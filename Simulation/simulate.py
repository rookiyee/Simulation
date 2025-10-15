import trimesh
import numpy as np
import pandas as pd
import os
from trimesh.boolean import boolean_manifold
import open3d as o3d
from numpy.linalg import norm
from numpy import deg2rad, ceil, concatenate
from projectManager import ProjectManager
from DataQuery import CNCDataQuery
from gcodeparsor import GcodeParser
from PyQt5.QtWidgets import QApplication, QMessageBox
import math

class Plant():
    def __init__(self):
        self.F_ym_hist = [0, 0]  # 存储 F_ym(i-2), F_ym(i-1)
        self.v_hist = [0, 0, 0]   # v(i-3), v(i-2), v(i-1)

    def plant(self, width, depth, n, v_current):
        # 計算切削力 F_ym(i)
        m = width * depth
        alpha = -m / (1 + m)/ 1.1
        n_rps = n / 60                # 轉/秒
        beta = 1 / (4 * n_rps) * (m / (m + 1))
        g0, g1, h1 = 0.8, 0.5, 0.1

        # 計算 F_ym(i) 的差分方程式
        F_ym_i = (-(alpha + h1) * self.F_ym_hist[-1] - 
                  (alpha * h1) * self.F_ym_hist[-2] + 
                  beta * g0 * self.v_hist[-2] + 
                  beta * g1 * self.v_hist[-3])
        return F_ym_i

    def run_plant(self, width, depth, spindle_speed, feedCommand):
        F_ym_i = self.plant(width, depth, spindle_speed, feedCommand)
        
        # 更新歷史數據
        self.F_ym_hist.append(F_ym_i)
        self.v_hist.append(feedCommand)
        
        # 保持歷史數據長度
        if len(self.F_ym_hist) > 3:
            self.F_ym_hist.pop(0)
        if len(self.v_hist) > 4:
            self.v_hist.pop(0)
        return F_ym_i
    
class SimpleCam(GcodeParser):
    def __init__(self):
        super().__init__()
        self.time = 0
        # self.cut_paths=[]
        self.spindle_speed = 2000
        self.feed = 300
        self.current_simulated_cutting_force = 0
        self.workpiece = None
        self.tool = None
        self.width = None
        self.depth = None
        self.MRR = None
        self.step = []
        self.workpiece_for_anime = []
        self.tool_for_anime = []
        self.cutting_parameters = []
        self.cutting_distance = []
        # self.GcodeVarialb = {'503': 10, '501': 20, '504': 30, '502': 40}
        self.c_center = None
        self.a_center = None
        self.final_workpiece_coords = []
        self.gcode = None
        self.simulation_step = 0.9
        self.pj_manager = ProjectManager()
        self.CuttingPara_query = None
        self.plant = None
        
    def initial_CuttingPara_query(self):
        self.CuttingPara_query = CNCDataQuery(data=self.cutting_parameters)

    def GcodeVarialbeSetting(self, variableName, variableValue):
        self.GcodeVarialb[variableName] = float(variableValue)
        
    def get_3Dmodel(self):
        return self.workpiece

    def alignment_workpiece_and_offset(self, workpiece_filePath, workpiece_offset):
        self.workpiece = trimesh.load_mesh(workpiece_filePath)
        origin_alignment_x = -self.workpiece.bounds[1][0] #工件原點和3D模型原點對齊
        origin_alignment_y = -self.workpiece.bounds[0][1]
        origin_alignment_z = -self.workpiece.bounds[0][2]
        self.workpiece.apply_translation([origin_alignment_x, origin_alignment_y, origin_alignment_z])

        if workpiece_offset[3] == ['', '', '']:
            workpiece_offset[3] = list(self.workpiece.centroid)
        if workpiece_offset[4] == ['', '', '']:
            workpiece_offset[4] = list(self.workpiece.centroid)
        order = workpiece_offset[2]
        self.c_center = workpiece_offset[3]
        self.a_center = workpiece_offset[4]
        
        angle_rad = np.deg2rad(workpiece_offset[0]) #C軸
        # 建立繞 X 軸的旋轉矩陣 A軸
        rotation_matrix_C = self.get_rotation_matrix_C(angle_rad, self.c_center)
        
        angle_rad = np.deg2rad(workpiece_offset[1]) #A軸
        # 建立繞 X 軸的旋轉矩陣 A軸
        rotation_matrix_A = self.get_rotation_matrix_A(angle_rad, self.a_center)
        # 套用變換
        if order == 1:
            self.workpiece.apply_transform(rotation_matrix_C)
            self.workpiece.apply_transform(rotation_matrix_A)
        else:
            self.workpiece.apply_transform(rotation_matrix_A)
            self.workpiece.apply_transform(rotation_matrix_C)
            
    def alignment_tool_and_offset(self, tool_filePath, tool_offset):
        self.tool = trimesh.load_mesh(tool_filePath)
        origin_alignment_x = -self.tool.bounds[0][0] #工件原點和3D模型原點對齊
        origin_alignment_y = -self.tool.bounds[0][1]
        origin_alignment_z = -self.tool.bounds[0][2]
        self.tool.apply_translation([origin_alignment_x, origin_alignment_y, origin_alignment_z])
        self.tool.apply_translation(tool_offset)
        
            
    def get_rotation_matrix_C(self, angle_rad, center):
        rotation_matrix_C = trimesh.transformations.rotation_matrix(
            angle_rad,       # 旋轉角度
            [0, 0, -1],       # 繞 Z 軸旋轉
            point=center  
        )
        return rotation_matrix_C
    
    def get_rotation_matrix_A(self, angle_rad, center):
        rotation_matrix_A = trimesh.transformations.rotation_matrix(
            angle_rad,       # 旋轉角度
            [1, 0, 0],       # 繞 X 軸旋轉
            point=center
        )
        return rotation_matrix_A
    
    def trimesh_to_open3d(self, mesh: trimesh.Trimesh) -> o3d.geometry.TriangleMesh:
        o3d_mesh = o3d.geometry.TriangleMesh()
        o3d_mesh.vertices = o3d.utility.Vector3dVector(mesh.vertices)
        o3d_mesh.triangles = o3d.utility.Vector3iVector(mesh.faces)
        return o3d_mesh
    
    def open3d_to_trimesh(self, o3d_mesh: o3d.geometry.TriangleMesh) -> trimesh.Trimesh:
        vertices = np.asarray(o3d_mesh.vertices)
        faces = np.asarray(o3d_mesh.triangles)
        return trimesh.Trimesh(vertices=vertices, faces=faces)
    
    def simplify_mesh(self, mesh: trimesh.Trimesh, max_faces=2000, method='auto', reduction_ratio=0.5, voxel_pitch=0.5) -> trimesh.Trimesh:
        if method == 'auto':
            if len(mesh.faces) <= max_faces:
                return mesh
            else:
                method = 'decimation'
    
        target_faces = int(max_faces * reduction_ratio)
    
        if method == 'decimation':
            o3d_mesh = self.trimesh_to_open3d(mesh)
            o3d_mesh.compute_vertex_normals()
            simplified = o3d_mesh.simplify_quadric_decimation(target_number_of_triangles=target_faces)
            print(f'simplified from {len(mesh.faces)} to {len(simplified.triangles)} faces')
            return self.open3d_to_trimesh(simplified)
    
        elif method == 'voxel':
            voxelized = mesh.voxelized(pitch=voxel_pitch)
            voxel_mesh = voxelized.as_boxes()
            return voxel_mesh
    
        else:
            raise ValueError(f"Unknown method: {method}")
    
    def calculate_cutting_volume(self, simulation_mode, progress, workpiece_filePath, tool_filePath, workpiece_offset, tool_offset, gcode=None, controller=''):
        self.plant = Plant()
        self.tool = self.simplify_mesh(self.tool, max_faces=2000, reduction_ratio=0.5)
        self.step = []
        self.final_workpiece_coords = []
        self.workpiece_for_anime = []
        self.tool_for_anime = []
        self.cutting_distance = []
        self.cutting_parameters = []
        self.epsilon = 1e-6
        self.time = 0
    
        workpiece_coord = np.array([0.0, 0.0, 0.0])
        workpiece_angle = np.array([0.0, 0.0])  # C A 軸
        progress_value = 0.0
    
        if gcode:
            self.gcode = gcode
            self.parse_gcode(self.gcode, controller)
    
        total_paths = len(self.cut_paths)
        # print(self.cut_paths)
        try:
            for i, path_info in enumerate(self.cut_paths):
                # 从新的数据结构中提取信息
                command = path_info['motion_mode']
                gcode_lineNumber = path_info['line_number']
                target_pose = path_info['target_pose']
                FeedCommand = path_info['feed']
                SpindleSpeed = path_info['spindle_speed']
                arc_params = path_info['arc_params']  # 圆弧参数
                current_tool = path_info['current_tool']  # 当前刀具
                
                self.feed, self.spindle_speed = FeedCommand, SpindleSpeed
                max_progress_increase = 1000.0 / total_paths
                vector = target_pose[:3] - workpiece_coord
                angle = target_pose[3:] - workpiece_angle
                magnitude = norm(vector)
                
                radius_c = norm(np.array([self.workpiece.bounds[1][0], self.workpiece.centroid[1], self.workpiece.centroid[2]]) - self.c_center)
                C_movement = radius_c * deg2rad(abs(angle[0]))
        
                radius_a = norm(np.array([self.workpiece.centroid[0], self.workpiece.centroid[1], self.workpiece.bounds[1][2]]) - self.a_center)
                A_movement = radius_a * deg2rad(abs(angle[1]))
        
                if magnitude == 0 and C_movement == 0 and A_movement == 0:
                    progress_value = max(0.0, progress_value + max_progress_increase)
                    progress.setValue(min(int(round(progress_value)), 1000))
                    progress.setFormat(f"{progress_value / 10:.1f} %")  # 顯示小數點一位
                    continue
        
                temp_cutting_parameters = []
        
                # 处理圆弧插补
                is_arc_move = command in ['G2', 'G3', 'G02', 'G03'] and arc_params
                
                if command == 'G0':
                    step = 5
                    effective_distance = max(magnitude, C_movement, A_movement)  # For G0, use magnitude
                    scale = effective_distance / step
                    step_vector = vector / step
                    step_angle = angle / step
                    angle_per_step_for_tool = 0
                elif is_arc_move:
                    # 圆弧插补处理
                    # 这里需要根据圆弧参数计算圆弧路径
                    # 目前先使用直线近似，后续可以完善圆弧插补算法
                    step = ceil(magnitude / self.simulation_step)
                    step = max(1, step)  # 防止 step = 0
                    scale = magnitude / step
                    step_vector = vector / step
                    step_angle = angle / step
                    time = scale / (self.feed / 60)
                    angle_per_step_for_tool = self.spindle_speed / 60 * 360 * time
        
                    self.cutting_distance.append(magnitude)
                    self.step.append(scale)
                    print(f"圆弧插补: {command}, 半径: {arc_params.get('R', 'N/A')}, 步数: {step}")
                else:
                    effective_distance = max(magnitude, C_movement, A_movement)
                    step = ceil(effective_distance / self.simulation_step)
                    step = max(1, step)  # 防止 step = 0
                    scale = effective_distance / step
                    step_vector = vector / step
                    step_angle = angle / step
                    time = scale / (self.feed / 60)
                    angle_per_step_for_tool = self.spindle_speed / 60 * 360 * time
        
                    self.cutting_distance.append(effective_distance)
                    self.step.append(scale)
        
                step_progress = max_progress_increase / step
        
                for step_index in range(int(step)):
                    # 对于圆弧插补，这里可以添加圆弧路径计算
                    # 目前先用直线插补近似
                    self.tool.apply_translation(step_vector)
                    if simulation_mode == 'Accurate':
                        time = scale / (self.feed / 60)
                        angle_per_step_for_tool = self.spindle_speed / 60 * 360 * time
                        self.tool.apply_transform(self.get_rotation_matrix_C(deg2rad(angle_per_step_for_tool), self.tool.centroid))
        
                    self.workpiece.apply_transform(
                        self.get_rotation_matrix_C(deg2rad(step_angle[0]), self.c_center) @
                        self.get_rotation_matrix_A(deg2rad(step_angle[1]), self.a_center)
                    )
                    if command == 'G0':
                        self.time += scale / (3000 / 60)
                    else:
                        self.time += scale / (self.feed / 60)
                    workpiece_coord += step_vector
                    workpiece_angle += step_angle
                    current_pose = concatenate((workpiece_coord, workpiece_angle))
                    self.final_workpiece_coords.append(current_pose)
        
                    try:
                        intersection = boolean_manifold([self.workpiece, self.tool], operation='intersection', check_volume=False)
        
                        if intersection.is_empty:
                            temp_cutting_parameters.append(concatenate((current_pose, [0, 0, 0, gcode_lineNumber, self.time, 0])))
                        else:
                            self.workpiece = self.simplify_mesh(self.workpiece)
                            self.workpiece = boolean_manifold([self.workpiece, self.tool], operation='difference', check_volume=False)
        
                            # Modified width and depth calculation
                            tool_axis = np.array([0.0, 0.0, 1.0])
                            omega_C = np.array([0.0, 0.0, deg2rad(step_angle[0])])
                            omega_A = np.array([deg2rad(step_angle[1]), 0.0, 0.0])
                            inter_centroid = intersection.centroid
                            disp_C = np.cross(omega_C, inter_centroid - self.c_center)
                            disp_A = np.cross(omega_A, inter_centroid - self.a_center)
                            feed_vector = disp_C + disp_A - step_vector
                            feed_norm = np.linalg.norm(feed_vector)
        
                            if feed_norm < self.epsilon:
                                width = 0.0
                                depth = 0.0
                                cross_area = 0.0  # Optional: set volume to 0 if no movement
                            else:
                                projs_z = np.dot(intersection.vertices, tool_axis)
                                depth = np.max(projs_z) - np.min(projs_z)
        
                                volume = intersection.volume
                                cross_area = volume / scale  # cross area
                                if simulation_mode == 'Accurate':
                                    width = cross_area / depth
                                else:
                                    unit_vector = feed_vector / feed_norm
                                    cross_dir = np.cross(tool_axis, unit_vector)
                                    cross_norm = np.linalg.norm(cross_dir)
                                    verts = intersection.vertices
                                    if cross_norm < self.epsilon:
                                        width = 0.0  # Plunging case
                                    else:
                                        width_dir = cross_dir / cross_norm
                                        projs = np.dot(verts, width_dir)
                                        width = np.max(projs) - np.min(projs)
        
                            self.current_simulated_cutting_force = self.plant.run_plant(width, depth, self.spindle_speed, self.feed)
                            temp_cutting_parameters.append(concatenate((current_pose, [width, depth, cross_area, gcode_lineNumber, self.time, self.current_simulated_cutting_force])))
        
                    except Exception as e:
                        print(e)
        
                    # 儲存動畫資料
                    self.workpiece_for_anime.append((self.workpiece.vertices, self.workpiece.faces))
                    self.tool_for_anime.append((self.tool.vertices, self.tool.faces))
        
                    # 修正：避免負數，使用 round
                    progress_value = max(0.0, progress_value + step_progress)
                    progress.setValue(min(int(round(progress_value)), 1000))
                    progress.setFormat(f"{progress_value / 10:.1f} %")  # 顯示小數點一位
        
                if temp_cutting_parameters:
                    self.cutting_parameters.append(temp_cutting_parameters)
        except Exception as e:
            parent = QApplication.activeWindow()  # 自動抓目前的活動視窗
            QMessageBox.critical(parent, "錯誤", f"{gcode_lineNumber}發生例外：{e}")
        
        try:
            base_path = self.pj_manager.get_base_path()
            save_dir = os.path.join(base_path, "TemporarySaved", "3d_model")
            os.makedirs(save_dir, exist_ok=True)  # 自動建立資料夾
            export_filepath = os.path.join(save_dir, "cutted_workpiece.stl")
            self.workpiece.export(export_filepath)
        
            if isinstance(self.cutting_parameters, list):
                self.cutting_parameters = np.concatenate(self.cutting_parameters, axis=0)
        
            base_path = self.pj_manager.get_base_path()
            save_dir = os.path.join(base_path, "TemporarySaved", "data")
            os.makedirs(save_dir, exist_ok=True)  # 自動建立資料夾
            export_filepath = os.path.join(save_dir, "all_cutting_parameters.csv")
            columns = ['X', 'Y', 'Z', 'C', 'A', 'Width', 'Depth', 'cross_area', 'GcodeLineNumber', 'Time', 'Simulated Cutting Force']
            df = pd.DataFrame(self.cutting_parameters, columns=columns)
            df.to_csv(export_filepath, index=False)
            self.initial_CuttingPara_query()
        except Exception as e:
            parent = QApplication.activeWindow()  # 自動抓目前的活動視窗
            QMessageBox.critical(parent, "錯誤", f"發生例外：{e}")
    
        # 強制收尾到 100%
        progress.setValue(1000)
        progress.setFormat(f"{1000 / 10:.1f} %")  # 顯示小數點一位
        return True