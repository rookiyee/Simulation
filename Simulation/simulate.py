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
from PyQt5.QtWidgets import QMessageBox
from math import atan2, sqrt, pi

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
    
    def calculate_center_ijk(self, start_point, end_point, arc_params):
        """
        處理圓心格式 (I, J, K)，並根據 G-code 規範重新計算半徑 R'。
        假設圓弧在 XY 平面 (G17)。
    
        返回: center (3D), radius (R')
        """
        start_xy = start_point[:2]
        end_xy = end_point[:2]
    
        # I, J 是圓心相對於起點的偏移量 (假設 G17: XY 平面)
        I = arc_params.get('I', 0.0)
        J = arc_params.get('J', 0.0)
        
        # 計算理論圓心 (C_theo) 和半徑 (R_start)
        center_xy = start_xy + np.array([I, J])
        
        # 圓心的 Z 座標：線性插補的 Z 軸運動不影響圓弧的 XY 旋轉中心
        # 這裡我們取起點的 Z
        center_z = start_point[2] 
        center = np.array([center_xy[0], center_xy[1], center_z])
        
        # 計算理論半徑 R_start 和 R_end
        R_start = norm(center_xy - start_xy)
        R_end = norm(center_xy - end_xy)
        
        # 根據 G-code 規範（圓心格式），新半徑 R' 是起點和終點距離的平均值
        R_prime = (R_start + R_end) / 2.0
        
        # 檢查是否為全圓：若目的地 X, Y, Z 沒給 (即 end_point == start_point)
        # 並且有 I, J 參數，則走全圓。
        is_full_circle = norm(end_point - start_point) < 1e-6 and (abs(I) > 1e-6 or abs(J) > 1e-6)
        
        # 檢查圓弧是否合理 (起點到圓心距離和終點到圓心距離是否接近)
        if abs(R_start - R_end) > 1e-3 and not is_full_circle:
            # e 是目標位置和圓心間的距離。如果誤差太大，表示 G-code 可能有問題
            print(f"Warning: IJK mode target position error e={abs(R_start - R_end):.4f}. Recalculating radius to R'={R_prime:.4f}")
    
        # 圓心不變，半徑使用 R'
        return center, R_prime, is_full_circle

    def calculate_center_r(self, start_point, end_point, R_value, command):
        """
        處理半徑格式 (R)。
        根據 R 的正負決定圓弧大小 (<180 或 >180)，並處理 R_ 值太小 d > 2R 的情況。
        假設圓弧在 XY 平面 (G17)。
    
        返回: center (3D), radius (R), is_linear_move (bool, 是否退化為 G1)
        """
        start_xy = start_point[:2]
        end_xy = end_point[:2]
        D = norm(end_xy - start_xy)  # 弦長 d
    
        R = abs(R_value)
        is_linear_move = False
        
        # 1. R = 0 處理
        if R < 1e-6:
            print("R mode: R=0, reverting to G1 linear move.")
            return start_point, 0.0, True
    
        # 2. R 值太小 (d > 2R) 處理
        if D > 2 * R + 1e-6:
            print(f"R mode: d={D:.4f} > 2R={2*R:.4f}. Performing semi-circle (R) then linear move (G1).")
            # 根據規範，先走半圓 (半徑為 R) 到某點，再以直線走到目的地。
            # 由於這個模擬步驟需要拆分成兩個路徑 (G2/G3 半圓 + G1 直線)，
            # 這裡我們只處理 G2/G3 的半圓部分，並在主循環中調整路徑。
            
            # 這裡返回的是半圓的圓心。半圓的圓心剛好是弦長的中點。
            center_xy = (start_xy + end_xy) / 2
            center_z = start_point[2]
            center = np.array([center_xy[0], center_xy[1], center_z])
            # 註：這裡計算的 center 和 R_value 的含義與實際 G-code 規範略有不同，
            # 因為我們需要一個明確的半圓路徑。
            # 由於我們沒有中間點資訊，**無法模擬 G-code 規範中的 "先走半圓再走直線"**。
            # 
            # **實務簡化**: 在模擬中，如果 $d > 2R$ 且 $R \ne 0$，通常被視為一個**錯誤**或**退化為直線**
            # 
            # **根據規範**: "先走以 R_ 值為半徑的半圓，然後再以直線走到目的地"
            # 由於這需要修改 `self.cut_paths` (即加入一個新的 G1 路徑)，這超出了當前函數的範圍。
            # 
            # **我們必須退化為 G1** 來保持模擬代碼的簡潔性。
            is_linear_move = True
            return start_point, 0.0, is_linear_move
        
        # 3. 正常狀態 (d <= 2R)
        
        # 計算弦高 h (圓心到弦中點的距離)
        # h^2 = R^2 - (D/2)^2
        h_squared = R**2 - (D/2)**2
        h = sqrt(h_squared) if h_squared >= 0 else 0
        
        mid_point_xy = (start_xy + end_xy) / 2
        
        # 弦的中垂線方向向量 (從start_xy到end_xy向量的逆時針90度)
        chord_vec = end_xy - start_xy
        perp_vec = np.array([-chord_vec[1], chord_vec[0]])
        perp_vec_norm = norm(perp_vec)
        
        # 如果起點和終點重合，則需要全圓 (應該在主函數中判斷)
        if perp_vec_norm < 1e-6:
            # 如果是全圓 (start == end)，圓心計算依賴於外部邏輯 (R 模式不能走全圓)
            raise ValueError("R mode: Start and end points are too close for arc definition.")
        
        unit_perp_vec = perp_vec / perp_vec_norm
        
        # 決定圓心方向：
        # G3 (CCW) -> 掃掠角 <= 180度時，h 向量方向為 unit_perp_vec
        # G2 (CW) -> 掃掠角 <= 180度時，h 向量方向為 -unit_perp_vec
        
        # 判斷是否大於 180 度 (R_value < 0)
        is_major_arc = R_value < 0 
        
        # 決定 h 的方向向量 (h_vec)
        h_vec = h * unit_perp_vec
        
        if is_major_arc:
            # > 180度弧長:
            # G3: 圓心在 -h_vec 方向
            # G2: 圓心在 h_vec 方向
            if command in ['G3', 'G03']: # CCW
                center_xy = mid_point_xy - h_vec
            else: # G2, CW
                center_xy = mid_point_xy + h_vec
        else:
            # <= 180度弧長:
            # G3: 圓心在 h_vec 方向
            # G2: 圓心在 -h_vec 方向
            if command in ['G3', 'G03']: # CCW
                center_xy = mid_point_xy + h_vec
            else: # G2, CW
                center_xy = mid_point_xy - h_vec
                
        center_z = start_point[2] 
        center = np.array([center_xy[0], center_xy[1], center_z])
        
        return center, R, is_linear_move
    
    def get_arc_params(self, start_point, end_point, arc_params, command):
        """
        統一處理 IJK/R 模式的圓弧計算，並處理特殊情況。
        返回: center (3D), radius, sweep_angle_rad, arc_length, is_linear_move
        """
        is_linear_move = False
        
        if 'R' in arc_params:
            # R 模式
            R_value = arc_params['R']
            try:
                center, radius, is_linear_move = self.calculate_center_r(start_point, end_point, R_value, command)
            except ValueError:
                is_linear_move = True
        elif 'I' in arc_params and 'J' in arc_params:
            # IJK 模式
            try:
                center, radius, is_full_circle = self.calculate_center_ijk(start_point, end_point, arc_params)
            except ValueError:
                is_linear_move = True
                is_full_circle = False
            
            # 圓心格式特殊情況：I=J=0，退化為 G1
            if not is_full_circle and (arc_params.get('I', 0.0) == 0.0 and arc_params.get('J', 0.0) == 0.0):
                is_linear_move = True
    
            if is_full_circle and not is_linear_move:
                # 全圓：掃掠角度為 2*pi
                arc_length = 2 * pi * radius
                sweep_angle_rad = 2 * pi if command in ['G3', 'G03'] else -2 * pi
                # 由於終點==起點，我們不需要 get_arc_angle_length
                return center, radius, sweep_angle_rad, arc_length, False
    
        else:
            # 沒有足夠的圓弧參數，退化為 G1
            is_linear_move = True
    
        if is_linear_move:
            # 退化為 G1 的情況：center, radius, sweep_angle, arc_length 都是虛擬值
            # magnitude 是直線距離，用於 G1 計算
            magnitude = norm(end_point - start_point)
            return start_point, 0.0, 0.0, magnitude, True
        
        # 正常圓弧或 IJK 模式的半徑修正後
        try:
            _, _, sweep_angle_rad, arc_length = self.get_arc_angle_length(center, start_point, end_point, command)
        except ValueError as e:
            # 理論上不應該發生，但作為保護
            print(f"Error in arc angle calculation: {e}. Reverting to G1.")
            magnitude = norm(end_point - start_point)
            return start_point, 0.0, 0.0, magnitude, True
        
        return center, radius, sweep_angle_rad, arc_length, False
    
    def get_arc_angle_length(self, center, start_point, end_point, command):
        """
        計算圓弧的起始角、終止角、掃掠角度和弧長。
        此函數與前一個版本相同，用來計算角度。
        """
        center_xy = center[:2]
        start_xy = start_point[:2]
        end_xy = end_point[:2]
        
        # 計算半徑 (用來驗證起點終點是否在圓上)
        R_start = norm(start_xy - center_xy)
        R_end = norm(end_xy - center_xy)
        
        # 由於 IJK 模式已經將半徑修正為平均值 R'，這裡使用 R_start
        radius = R_start 
        
        # 計算起始角和終止角 (相對於圓心，在 XY 平面)
        start_angle = atan2(start_xy[1] - center_xy[1], start_xy[0] - center_xy[0])
        end_angle = atan2(end_xy[1] - center_xy[1], end_xy[0] - center_xy[0])
    
        # 調整角度為 0 到 2*pi
        if start_angle < 0:
            start_angle += 2 * pi
        if end_angle < 0:
            end_angle += 2 * pi
    
        # 計算掃掠角度 (Sweep Angle)
        if command in ['G2', 'G02']:  # 順時針 (CW)
            # G2 (CW) 應為負角度
            if start_angle > end_angle:
                sweep_angle = -(start_angle - end_angle)
            else:
                sweep_angle = -(2 * pi - (end_angle - start_angle))
                
        elif command in ['G3', 'G03']:  # 逆時針 (CCW)
            # G3 (CCW) 應為正角度
            if end_angle > start_angle:
                sweep_angle = end_angle - start_angle
            else:
                sweep_angle = (2 * pi - (start_angle - end_angle))
        else:
            raise ValueError("Invalid command for arc angle calculation. Must be G2 or G3.")
    
        # 計算弧長 (S = R * |theta|)
        arc_length = radius * abs(sweep_angle)
        
        return start_angle, end_angle, sweep_angle, arc_length


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
    
    def simplify_mesh(self, mesh: trimesh.Trimesh, max_faces=10000, method='auto', reduction_ratio=0.5, voxel_pitch=0.5) -> trimesh.Trimesh:
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
    
    def calculate_cutting_volume(self, simulation_mode, progress, workpiece_filePath, tool_filePath, workpiece_offset, tool_offset, gcode, controller, tool_dict, gcode_is_altered):
        self.plant = Plant()
        filepath = list(tool_dict.values())[0][0]  #第1把刀具檔案路徑
        self.alignment_tool_and_offset(filepath, tool_offset)
        self.tool = self.simplify_mesh(self.tool, max_faces=10000, reduction_ratio=0.5)
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
            if gcode_is_altered:
                self.parse_gcode(self.gcode, controller)

        total_paths = len(self.cut_paths)
        current_tool_id = ''
        # try:
        for i, path_info in enumerate(self.cut_paths):
            # 从新的数据结构中提取信息
            command = path_info['motion_mode']
            gcode_lineNumber = path_info['line_number']
            target_pose = path_info['target_pose']
            FeedCommand = path_info['feed']
            SpindleSpeed = path_info['spindle_speed']
            arc_params = path_info['arc_params']  # 圆弧参数
            current_tool = path_info['current_tool']  # 当前刀具的刀號字串
            if current_tool != None:
                if current_tool_id != current_tool:
                    current_tool_id = current_tool
                    self.alignment_tool_and_offset(tool_dict[current_tool_id][0], tool_offset)
                    self.tool = self.simplify_mesh(self.tool, max_faces=10000, reduction_ratio=0.5)
                    self.tool.apply_translation(workpiece_coord)
                    
                    
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
                # 圓弧插補處理 (G2/G3)
                start_point = workpiece_coord
                end_point = target_pose[:3]

                # 1. 統一計算圓弧參數，並處理 IJK/R 特殊情況
                center, radius, sweep_angle_rad, arc_distance, is_linear_move = self.get_arc_params(
                    start_point, end_point, arc_params, command
                )
                
                if is_linear_move:
                    # 圓弧退化為 G1 (直線) 或 R 模式 d > 2R 的簡化處理
                    is_arc_move = False # 確保進入 G1 邏輯
                    effective_distance = max(magnitude, C_movement, A_movement) # 直線距離
                else:
                    # 正常圓弧路徑
                    effective_distance = max(arc_distance, C_movement, A_movement)

                if is_arc_move:
                    # 2. 確定步數和每一小步的參數 (使用弧長 arc_distance)
                    step = ceil(effective_distance / self.simulation_step)
                    step = max(1, int(step))  # 防止 step = 0
                    
                    scale = arc_distance / step # 每一小步的弧長 (用於時間和體積計算)
                    step_angle_rad = sweep_angle_rad / step # 每一小步的掃掠角度 (XY 平面)
                    
                    # Z 軸的線性變化
                    step_z = vector[2] / step
                    
                    # C 軸和 A 軸的線性變化
                    step_angle = angle / step
                    
                    time = scale / (self.feed / 60)
                    angle_per_step_for_tool = self.spindle_speed / 60 * 360 * time
                    
                    self.cutting_distance.append(arc_distance)
                    self.step.append(scale)
                    # print(f"圓弧插補: {command}, 半徑: {radius:.3f}, 弧長: {arc_distance:.3f}, 步數: {step}")
                
            if not is_arc_move:
                # G1 或 G2/G3 退化為 G1 的情況
                effective_distance = max(magnitude, C_movement, A_movement)
                step = ceil(effective_distance / self.simulation_step)
                step = max(1, int(step))  # 防止 step = 0
                scale = effective_distance / step
                step_vector = vector / step
                step_angle = angle / step
                if self.feed and self.feed > 0:
                    time = scale / (self.feed / 60)
                else:
                    time = 0
                angle_per_step_for_tool = self.spindle_speed / 60 * 360 * time
                
                self.cutting_distance.append(effective_distance)
                self.step.append(scale)

            step_progress = max_progress_increase / step
            
            for step_index in range(int(step)):
                
                if command in ['G2', 'G3', 'G02', 'G03'] and is_arc_move:
                    # G2/G3 圓弧模擬
                    
                    # 1. 計算旋轉矩陣 (繞圓心)
                    rotation_matrix_xy_for_tool = trimesh.transformations.rotation_matrix(
                        step_angle_rad,  # 掃掠角度
                        [0, 0, 1],      # 繞 Z 軸旋轉 (假設 G17: XY 平面) 順時針
                        point=self.tool.centroid + (center - workpiece_coord)     # 圓心
                    )
                    
                    
                    # 2. 應用旋轉和平移
                    self.tool.apply_transform(rotation_matrix_xy_for_tool)
                    self.tool.apply_translation([0, 0, step_z])
                    
                    # 3. 計算實際移動向量 (用於更新 workpiece_coord)
                    # 找到目前刀具位置
                    current_tool_position = workpiece_coord
                    
                    point_to_rotate = np.array([current_tool_position]) 
                    
                    rotation_matrix_xy_for_coord_track = trimesh.transformations.rotation_matrix(
                        step_angle_rad,  # 掃掠角度
                        [0, 0, 1],      # 繞 Z 軸旋轉 (假設 G17: XY 平面) 順時針
                        point=center     # 圓心
                    )
                    # 旋轉後的 XY 位置
                    # 註：transform_points 返回的也是 N x 3 數組，我們取第一個點的 XYZ
                    rotated_point = trimesh.transformations.transform_points(
                        point_to_rotate, 
                        rotation_matrix_xy_for_coord_track
                    )[0] # [0] 取得單個點的 [X, Y, Z] 陣列
                    
                    # 新的刀具位置 (旋轉後的 XY + Z 平移)
                    new_tool_position = rotated_point + np.array([0, 0, step_z])
                    
                    step_vector_actual = new_tool_position - current_tool_position
                    
                else:
                    # G0/G1 (或 G2/G3 退化) 的線性模擬
                    self.tool.apply_translation(step_vector)
                    step_vector_actual = step_vector
                
                # 刀具主軸旋轉 (C 軸)
                if simulation_mode == 'Accurate':
                    # ... (刀具主軸旋轉代碼不變)
                    time = scale / (self.feed / 60) # 使用弧長或有效距離
                    angle_per_step_for_tool = self.spindle_speed / 60 * 360 * time
                    self.tool.apply_transform(self.get_rotation_matrix_C(deg2rad(angle_per_step_for_tool), self.tool.centroid))
                
                # 工件 C/A 軸旋轉
                self.workpiece.apply_transform(
                    self.get_rotation_matrix_C(deg2rad(step_angle[0]), self.c_center) @
                    self.get_rotation_matrix_A(deg2rad(step_angle[1]), self.a_center)
                )

                # ... (時間計算)
                if command == 'G0':
                    self.time += norm(step_vector_actual) / (3000 / 60) # 使用實際移動距離
                else:
                    self.time += scale / (self.feed / 60) # 使用弧長或有效距離

                # 更新工件座標 (即刀具的絕對位置)
                workpiece_coord += step_vector_actual
                workpiece_angle += step_angle
                current_pose = concatenate((workpiece_coord, workpiece_angle))
                self.final_workpiece_coords.append(current_pose)
    
                # try:
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
                    feed_vector = disp_C + disp_A - step_vector_actual
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
                    if self.spindle_speed == 0:
                        self.current_simulated_cutting_force = 0 
                    else:
                        self.current_simulated_cutting_force = self.plant.run_plant(width, depth, self.spindle_speed, self.feed)
                    temp_cutting_parameters.append(concatenate((current_pose, [width, depth, cross_area, gcode_lineNumber, self.time, self.current_simulated_cutting_force])))
    
                # except Exception as e:
                #     print(e)
    
                # 儲存動畫資料
                self.workpiece_for_anime.append((self.workpiece.vertices, self.workpiece.faces))
                self.tool_for_anime.append((self.tool.vertices, self.tool.faces))
    
                # 修正：避免負數，使用 round
                progress_value = max(0.0, progress_value + step_progress)
                progress.setValue(min(int(round(progress_value)), 1000))
                progress.setFormat(f"{progress_value / 10:.1f} %")  # 顯示小數點一位
    
            if temp_cutting_parameters:
                self.cutting_parameters.append(temp_cutting_parameters)
        # except Exception as e:
        #     print('2',e)
            # parent = QApplication.activeWindow()  # 自動抓目前的活動視窗
            # QMessageBox.critical(parent, "錯誤", f"{gcode_lineNumber}發生例外：{e}")
        
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
            print('3', e)
            # parent = QApplication.activeWindow()  # 自動抓目前的活動視窗
            # QMessageBox.critical(parent, "錯誤", f"發生例外：{e}")
    
        # 強制收尾到 100%
        progress.setValue(1000)
        progress.setFormat(f"{1000 / 10:.1f} %")  # 顯示小數點一位
        return True