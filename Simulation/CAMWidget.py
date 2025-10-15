import os
import time
import threading
import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from simulate import SimpleCam
import requests
import pandas as pd
from projectManager import ProjectManager
# PyQt5
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton,
    QProgressBar, QLabel, QTextEdit, QFrame, QSlider, QMessageBox, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, QCoreApplication
from PyQt5.QtGui import QColor, QTextCursor, QTextCharFormat

# Matplotlib
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar


class SimulationWidget(QWidget):
    """可嵌入的模拟界面组件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.cnc = SimpleCam()
        self.pj_manager = ProjectManager()
        self.settings = {
            'Workpiece': '',
            'Tool': '',
            'Gcode': [],
            'Controller': '',
            'Workpiece Orientation': [0, 0, 1, ['', '', ''], ['', '', '']],
            'Workpiece Offset': [0, 0, 0],
            'STH Signal': '',
            '2DPlot_Column_choose': [0, 1],
            'All Cutting Parameters': '',
            'workpiece_for_anime': '',
            'tool_for_anime': '',
            'simulation_step': 0.9,
            'Simulation Mode': 'Simplified',
            'STH data Synchronized range': ['', '']
        }
        self.workpiece_isPrepared = False
        self.tool_isPrepared = False
        self.gcode_isPrepared = False
        self.Workpiece_Orientation_isPrepared = False
        self.Workpiece_Offset_isPrepared = False
        self.actor_workpiece = None
        self.actor_tool = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_frame)  # 每次 timeout 呼叫 next_frame
        self.play_speed = 100
    
    def setup_ui(self):
        """设置界面布局和组件"""
        main_vertical_layout = QVBoxLayout()
        self.setLayout(main_vertical_layout)
        # 创建主网格布局 (3行3列)
        main_layout = QGridLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        self.setLayout(main_layout)
        
        # 设置列和行的比例
        main_layout.setColumnStretch(0, 3)  # 第一列占3份
        main_layout.setColumnStretch(1, 3)  # 第二列占3份
        main_layout.setColumnStretch(2, 2)  # 第三列占2份 (总比例3:3:2，即37.5%:37.5%:25%)
        
        main_layout.setRowStretch(0, 1)  # 第一行占1份
        main_layout.setRowStretch(1, 5)  # 第二行占5份
        main_layout.setRowStretch(2, 3)  # 第三行占3份
        
        # 添加组件到网格布局
        self.create_simulate_button(main_layout)        # (0,0)
        self.create_progress_bar(main_layout)           # (0,1) 跨2列
        self.create_3d_plot(main_layout)                # (1,0) 跨1行2列
        self.create_2d_plot1(main_layout)               # (2,0)
        self.create_2d_plot2(main_layout)               # (2,1)
        self.create_gcode_input(main_layout)            # (1,2) 跨2行
        # 将网格布局添加到主垂直布局
        main_vertical_layout.addLayout(main_layout)
        
        # 添加可拖动的进度条在底部
        self.create_frame_slider(main_vertical_layout)
    
    def create_frame_slider(self, layout):
        """创建基于图片张数的滑块"""
        # 创建包含滑块和标签的水平布局
        hbox = QHBoxLayout()
        hbox.setContentsMargins(10, 5, 10, 10)
    
        # 添加帧数标签
        self.frame_label = QLabel("Frame: 0/100")
        self.frame_label.setAlignment(Qt.AlignCenter)
        self.frame_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 3px;
            }
        """)
        # 自适应宽度
        self.frame_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        hbox.addWidget(self.frame_label)
    
        # 创建滑块
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setEnabled(False)
        self.frame_slider.setRange(0, 100)
        self.frame_slider.setValue(0)
        self.frame_slider.setTickPosition(QSlider.TicksBelow)
        self.frame_slider.setTickInterval(1)
        self.frame_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #bbb;
                background: white;
                height: 10px;
                border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background: #2196F3;
                border-radius: 4px;
            }
            QSlider::add-page:horizontal {
                background: #f0f0f0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #fff;
                border: 1px solid #777;
                width: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #f8f8f8;
                border: 1px solid #2196F3;
            }
        """)
    
        # 连接滑块值改变信号
        self.frame_slider.valueChanged.connect(self.on_scale_move)
    
        hbox.addWidget(self.frame_slider, 1)  # 滑块占据剩余空间
    
        # 添加控制按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(5)
    
        self.btn_prev = QPushButton("<<")
        self.btn_prev.setFixedWidth(40)
        self.btn_prev.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 3px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        self.btn_prev.clicked.connect(self.decelerate_play)
    
        self.btn_play = QPushButton("Play")
        self.btn_play.setFixedWidth(60)
        self.btn_play.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                border-radius: 3px;
                padding: 3px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.btn_play.clicked.connect(self.toggle_play)
    
        self.btn_next = QPushButton(">>")
        self.btn_next.setFixedWidth(40)
        self.btn_next.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 3px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        self.btn_next.clicked.connect(self.accelerate_play)
    
        btn_layout.addWidget(self.btn_prev)
        btn_layout.addWidget(self.btn_play)
        btn_layout.addWidget(self.btn_next)
    
        hbox.addLayout(btn_layout)
    
        # 添加到主布局
        layout.addLayout(hbox)

    
    def accelerate_play(self):
        if self.play_speed/2 > 10:
            self.play_speed /= 2
        else:
            self.play_speed = 10
    def decelerate_play(self):
        if self.play_speed*2 < 500:
            self.play_speed *= 2
        else:
            self.play_speed = 500
    # def prev_frame(self):
    #     """显示上一帧"""
    #     if self.frame_slider.isEnabled():
    #         current = self.frame_slider.value()
    #         if current > 0:
    #             self.frame_slider.setValue(current - 1)
    
    def next_frame(self):
        """显示下一帧"""
        if self.frame_slider.isEnabled():
            current = self.frame_slider.value()
            if current < self.frame_slider.maximum():
                self.frame_slider.setValue(current + 1)
            else:
                self.timer.stop()
                self.btn_play.setText("Play")  # 若到達最後一幀自動停下
                self.btn_play.setStyleSheet("""
                    QPushButton {
                        background-color: #4CAF50;
                        color: white;
                        font-weight: bold;
                        border-radius: 3px;
                        padding: 3px;
                    }
                    QPushButton:hover {
                        background-color: #45a049;
                    }
                """)
    
    def toggle_play(self):
        """切换播放/暂停状态"""
        if self.frame_slider.isEnabled():
            if self.btn_play.text() == "Play":
                self.btn_play.setText("Pause")
                self.btn_play.setStyleSheet("""
                    QPushButton {
                        background-color: #FF9800;
                        color: white;
                        font-weight: bold;
                        border-radius: 3px;
                        padding: 3px;
                    }
                    QPushButton:hover {
                        background-color: #e68a00;
                    }
                """)
                # 这里可以启动动画播放
                self.timer.start(int(self.play_speed))  # 每 100 毫秒切換一幀
            else:
                self.btn_play.setText("Play")
                self.btn_play.setStyleSheet("""
                    QPushButton {
                        background-color: #4CAF50;
                        color: white;
                        font-weight: bold;
                        border-radius: 3px;
                        padding: 3px;
                    }
                    QPushButton:hover {
                        background-color: #45a049;
                    }
                """)
                # 这里可以停止动画播放
                self.timer.stop()
            
    def create_simulate_button(self, layout):
        """创建模拟按钮 (0,0)"""
        self.btn_simulate = QPushButton("Simulate")
        self.btn_simulate.setFixedHeight(40)
        self.btn_simulate.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.btn_simulate.clicked.connect(self.CalculateButton_Onclick)
        layout.addWidget(self.btn_simulate, 0, 0)
    
    def create_progress_bar(self, layout):
        """创建进度条 (0,1) 跨2列"""
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 5px;
                text-align: center;
                background-color: #f0f0f0;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                width: 10px;
            }
        """)
        layout.addWidget(self.progress_bar, 0, 1, 1, 2)  # 跨1行2列
    
    def create_3d_plot(self, layout):
        """创建PyVista 3D绘图 (1,0) 跨1行2列"""
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setLineWidth(1)
        frame.setStyleSheet("background-color: white; border: 1px solid #ccc;")
        vbox = QVBoxLayout(frame)
        
        # 创建PyVista交互式3D视图
        self.plotter_3d = QtInteractor(frame)
        vbox.addWidget(self.plotter_3d)
        
        # 添加示例3D图形
        self.add_example_3d_plot()
        
        # 关键修改：只跨1行2列 (行1, 列0-1)
        layout.addWidget(frame, 1, 0, 1, 2)  # 跨1行2列
    
    def add_example_3d_plot(self):
        # 添加坐标轴
        self.plotter_3d.add_axes()
        self.plotter_3d.set_scale(xscale=1, yscale=1, zscale=1)  # 確保三軸等比例
        # 添加边界框
        # self.plotter_3d.add_bounding_box(color='gray', line_width=1)
        
        # 重置相机
        self.plotter_3d.reset_camera()
        
        # 设置背景色
        self.plotter_3d.set_background('white')
    
    def create_2d_plot1(self, layout):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("background-color: white; border: 1px solid #ccc;")
        
        vbox = QVBoxLayout(frame)
        vbox.setContentsMargins(5, 5, 5, 5)
    
        fig = Figure(figsize=(5, 3))
        fig.tight_layout()
        self.canvas1 = FigureCanvas(fig)
        self.ax1 = fig.add_subplot(111)
        self.ax1.set_title("Radial Cutting Depth", fontsize=9)
        self.axvline1 = None
        self.line_plot1 = None
        fig.subplots_adjust(bottom=0.2)
        self.toolbar1 = NavigationToolbar(self.canvas1, frame)
        vbox.addWidget(self.toolbar1)
        vbox.addWidget(self.canvas1)
    
        layout.addWidget(frame, 2, 0)
            
    def create_2d_plot2(self, layout):
        """创建第二个2D Matplotlib绘图 (2,1)"""
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("background-color: white; border: 1px solid #ccc;")
        vbox = QVBoxLayout(frame)
        vbox.setContentsMargins(5, 5, 5, 5)
        
        # 创建Matplotlib画布
        fig = Figure(figsize=(5, 3))
        fig.tight_layout()
        self.canvas2 = FigureCanvas(fig)
        self.ax2 = fig.add_subplot(111)
        self.ax2.set_title("Axial Cutting Depth", fontsize=9)
        self.axvline2 = None
        self.line_plot2 = None
        fig.subplots_adjust(bottom=0.2)
        self.toolbar2 = NavigationToolbar(self.canvas2, frame)
        vbox.addWidget(self.toolbar2)
        vbox.addWidget(self.canvas2)
    
        layout.addWidget(frame, 2, 1)
    
    def create_gcode_input(self, layout):
        """创建Gcode输入区域 (1,2) 跨2行，占宽度25%"""
        container = QWidget()
        container.setStyleSheet("background-color: white; border: 1px solid #ccc;")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(5, 5, 5, 5)
        
        # 添加标题
        lbl_title = QLabel("Gcode:")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("""
            QLabel {
                font-weight: bold; 
                font-size: 14px;
                padding: 5px;
                background-color: #f0f0f0;
                border-bottom: 1px solid #ccc;
            }
        """)
        vbox.addWidget(lbl_title)
        
        
        # 添加文本编辑区域
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Enter G-code here...")
        # 禁用自動換行
        self.text_edit.setLineWrapMode(QTextEdit.NoWrap)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                font-family: Consolas; 
                font-size: 12px;
                border: 1px solid #ddd;
                padding: 5px;
            }
        """)
        
        vbox.addWidget(self.text_edit)
        
        # 添加到主布局 (跨2行)
        layout.addWidget(container, 1, 2, 2, 1)
    
    def get_gcode(self):
        """获取Gcode文本"""
        return self.text_edit.toPlainText()
    
    def set_gcode(self, text):
        """设置Gcode文本"""
        self.text_edit.setText(text)
    
    def update_3d_plot(self, mesh):
        """更新3D绘图"""
        self.plotter_3d.clear()
        self.plotter_3d.add_mesh(mesh)
        self.plotter_3d.reset_camera()
    
    def update_2d_plot1(self, x, y, title=""):
        """更新第一个2D绘图"""
        if self.line_plot1:
            for line in self.line_plot1:
                line.remove()  # 對每個 Line2D 呼叫 remove()
        self.line_plot1 = self.ax1.plot(x, y, 'b')
        unit = 'mm'
        if self.settings['2DPlot_Column_choose'][0] == 0:
            title = "Radial Cutting Depth"
            unit = 'mm'
        elif self.settings['2DPlot_Column_choose'][0] == 1:
            title = "Axial Cutting Depth"
            unit = 'mm'
        elif self.settings['2DPlot_Column_choose'][0] == 2:
            title = "Cutting Cross-Sectional Area"
            unit = 'mm^2'
        elif self.settings['2DPlot_Column_choose'][0] in (3, 4, 5, 6):
            title = f"STH Signal CH{self.settings['2DPlot_Column_choose'][0]-2}"
            unit = 'volt'
        elif self.settings['2DPlot_Column_choose'][0] == 7:
            title = "Simulated Cutting Force"
            unit = 'kN'
            
        self.ax1.set_title(title, fontsize=9)
        self.ax1.grid(True, linestyle='--', alpha=0.7)
        self.ax1.set_xlabel("time(s)", fontsize=9)
        self.ax1.set_ylabel(unit, fontsize=9)
        self.ax1.set_xlim(0, x.max())
        y_min = y.min()
        y_max = y.max()
        self.ax1.set_ylim(y_min - y_min*0.1, y_max + y_max*0.1)
        self.canvas1.draw()
    
    def update_2d_plot2(self, x, y, title=""):
        """更新第一个2D绘图"""
        if self.line_plot2:
            for line in self.line_plot2:
                line.remove()  # 對每個 Line2D 呼叫 remove()
        self.line_plot2 = self.ax2.plot(x, y, 'b')
        unit = 'mm'
        if self.settings['2DPlot_Column_choose'][1] == 0:
            title = "Radial Cutting Depth"
            unit = 'mm'
        elif self.settings['2DPlot_Column_choose'][1] == 1:
            title = "Axial Cutting Depth"
            unit = 'mm'
        elif self.settings['2DPlot_Column_choose'][1] == 2:
            title = "Cutting Cross-Sectional Area"
            unit = 'mm^2'
        elif self.settings['2DPlot_Column_choose'][1] in (3, 4, 5, 6):
            title = f"STH Signal CH{self.settings['2DPlot_Column_choose'][1]-2}"
            unit = 'volt'
        elif self.settings['2DPlot_Column_choose'][1] == 7:
            title = "Simulated Cutting Force"
            unit = 'kN'
        
        self.ax2.set_title(title, fontsize=9)
        self.ax2.grid(True, linestyle='--', alpha=0.7)
        self.ax2.set_xlabel("time(s)", fontsize=9)
        self.ax2.set_ylabel(unit, fontsize=9)
        self.ax2.set_xlim(0, x.max())
        y_min = y.min()
        y_max = y.max()
        self.ax2.set_ylim(y_min - y_min*0.1, y_max + y_max*0.1)
        self.canvas2.draw()
        
    def Get_Gcode_form_CNC(self):
        response = requests.post('http://127.0.0.1:8001/Machine/GetGcode?MachineIP=192.168.104.30')
        data = response.json()
        return data[0]['gcode']
    def connect_cnc(self):
        self.settings['Gcode'] = self.Get_Gcode_form_CNC().splitlines()
        self.display_gcode()
    
    def display_gcode(self, file_path=None, isReadFile=False, chunk_size=10000):
        self.text_edit.clear()
    
        # === 模式 1: 讀檔 + 顯示 ===
        if isReadFile:
            if not file_path:
                return
    
            self.settings['Gcode'] = []   # 儲存完整內容
            buffer = []
    
            with open(file_path, 'r', encoding='utf-8') as file:
                for i, line in enumerate(file):
                    self.settings['Gcode'].append(line)
                    buffer.append(line)

                    # 每 chunk_size 行更新一次 UI
                    if (i + 1) % chunk_size == 0:
                        self.text_edit.append(''.join(buffer))
                        buffer.clear()
                        QCoreApplication.processEvents()

                # 顯示最後一批
                if buffer:
                    self.text_edit.append(''.join(buffer))
                    QCoreApplication.processEvents()
    
        # === 模式 2: 僅顯示既有內容 ===
        else:
            buffer = []
            for i, line in enumerate(self.settings['Gcode']):
                buffer.append(line)
                if (i + 1) % chunk_size == 0:
                    self.text_edit.append(''.join(buffer))
                    buffer.clear()
                    QCoreApplication.processEvents()
    
            if buffer:
                self.text_edit.append(''.join(buffer))
                QCoreApplication.processEvents()
                
        self.gcode_isPrepared = True
    
    def find_nearest_index(self, points, target):
        points = np.asarray(points)
        target = np.asarray(target)
        distances = np.linalg.norm(points - target, axis=1)
        return np.argmin(distances)

    def trimesh_to_pv(self, vertices, faces):
        n_faces = faces.shape[0]
        faces_flat = np.hstack([np.full((n_faces, 1), 3), faces]).astype(np.int64).flatten()
        return pv.PolyData(vertices, faces_flat)
    
    def plot_workpiece_mesh(self):
        filepath = self.settings['Workpiece']
        self.cnc.alignment_workpiece_and_offset(filepath, self.settings['Workpiece Orientation'])
        
        w_vertices = self.cnc.workpiece.vertices
        w_faces = self.cnc.workpiece.faces
        mesh_pv = self.trimesh_to_pv(w_vertices, w_faces)
        if self.actor_workpiece:
            self.plotter_3d.remove_actor(self.actor_workpiece)
        self.actor_workpiece = self.plotter_3d.add_mesh(mesh_pv, color='lightblue', show_edges=False)
    def import_workpiece(self):
        filepath = self.settings['Workpiece']
        is_verified = True
        if filepath == '':
            QMessageBox.warning(self, '提示', 'Workpiece has not imported!')
            is_verified = False
        elif not os.path.exists(filepath):
            QMessageBox.warning(self, '提示', 'Workpiece FilePath does\'t exist!')
            is_verified = False
        if not is_verified:
            return
        self.plot_workpiece_mesh()
        self.workpiece_isPrepared = True
    def to_STH_index(self, input_index):
        input_workpiece_coordinate = self.cnc.cutting_parameters[input_index, :3]
        output_index = self.find_nearest_index(self.XYZ_data, input_workpiece_coordinate)
        return output_index
    
    def import_STH_data(self):
        if self.settings['STH Signal'] != '':
            filepath = self.settings['STH Signal']
            self.STH_data = pd.read_csv(filepath)
            self.STH_data = np.array(self.STH_data)
            self.XYZ_data = self.STH_data[:, 4:7]
    def create_STH_time_array(self):
        self.STH_time = self.cnc.CuttingPara_query.batch_query(self.XYZ_data, 'time')
        return self.STH_time
            
    def synchronize_STH_signal(self):
        filepath = self.settings['STH Signal']
        is_verified = True
        if filepath == '':
            QMessageBox.warning(self, '提示', 'STH signal has not imported!')
            is_verified = False
        elif not os.path.exists(filepath):
            QMessageBox.warning(self, '提示', 'STH signal FilePath does\'t exist!')
            is_verified = False
        if not is_verified:
            return
        
        start_index = int(self.settings['STH data Synchronized range'][0])
        end_index = int(self.settings['STH data Synchronized range'][1])
        start_workpiece_coordinate = self.cnc.cutting_parameters[start_index, :3]
        end_workpiece_coordinate = self.cnc.cutting_parameters[end_index, :3]
        # self.STH_data = pd.read_csv(filepath)
        # self.STH_data = np.array(self.STH_data)
        # self.XYZ_data = self.STH_data[:, 4:7]
        start_export_index = self.find_nearest_index(self.XYZ_data, start_workpiece_coordinate)
        end_export_index = self.find_nearest_index(self.XYZ_data, end_workpiece_coordinate)
        
        columns = [f"Channel{i+1}" for i in range(4)] + ["X", "Y", "Z"]
        df = pd.DataFrame(self.STH_data[start_export_index:end_export_index+1], columns=columns)
        STH_dict = self.cnc.CuttingPara_query.batch_query(self.XYZ_data[start_export_index:end_export_index+1], ('width', 'depth', 'area', 'GcodeLine', 'time'))
        
        df['Width'] = STH_dict['width']
        df['Depth'] = STH_dict['depth']
        df['cross_area'] = STH_dict['area']
        df['GcodeLineNumber'] = STH_dict['GcodeLine']
        df['Time'] = STH_dict['time']
        # 存成 CSV
        base_path  = self.pj_manager.get_base_path()
        save_dir = os.path.join(base_path, "TemporarySaved", "data")
        os.makedirs(save_dir, exist_ok=True)  # 自動建立資料夾
        export_filepath = os.path.join(save_dir, "synchronize_STH_signal.csv")
        df.to_csv(export_filepath, index=False)
        QMessageBox.information(self, "匯出成功", f"已成功匯出至:\n{export_filepath}")
        
    def plot_tool_mesh(self):
        filepath = self.settings['Tool']
        self.cnc.alignment_tool_and_offset(filepath, self.settings['Workpiece Offset'])
        t_vertices = self.cnc.tool.vertices
        t_faces = self.cnc.tool.faces
        mesh_pv = self.trimesh_to_pv(t_vertices, t_faces)
        if self.actor_tool:
            self.plotter_3d.remove_actor(self.actor_tool)
        self.actor_tool = self.plotter_3d.add_mesh(mesh_pv, color='lightblue', show_edges=False)
        
    def import_tool(self):
        filepath = self.settings['Tool']
        is_verified = True
        if filepath == '':
            QMessageBox.warning(self, '提示', 'Tool has not imported!')
            is_verified = False
        elif not os.path.exists(filepath):
            QMessageBox.warning(self, '提示', 'Tool FilePath does\'t exist!')
            is_verified = False
        if not is_verified:
            return
        self.plot_tool_mesh()
        self.tool_isPrepared = True
     
    def set_workpiece_offset(self):
        filepath = self.settings['Tool']
        is_verified = True
        if filepath == '':
            QMessageBox.warning(self, '提示', 'Tool has not imported!')
            is_verified = False
        elif not os.path.exists(filepath):
            QMessageBox.warning(self, '提示', 'Tool FilePath does\'t exist!')
            is_verified = False
        if not is_verified:
            return False
        else:
            self.cnc.alignment_tool_and_offset(filepath, self.settings['Workpiece Offset'])
            self.Workpiece_Offset_isPrepared = True
            return True
        
    
    def set_Workpiece_Orientation(self):
        self.workpiece_offset = self.settings['Workpiece Orientation']
        filepath = self.settings['Workpiece']
        is_verified = True
        if filepath == '':
            QMessageBox.warning(self, '提示', 'Workpiece has not imported!')
            is_verified = False
        elif not os.path.exists(filepath):
            QMessageBox.warning(self, '提示', 'Workpiece FilePath does\'t exist!')
            is_verified = False
        if not is_verified:
            return False
        else:
            self.cnc.alignment_workpiece_and_offset(filepath, self.workpiece_offset)
            self.Workpiece_Orientation_isPrepared = True
            return True
    
    def highlight_line(self, line_number):
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.Start)
        
        for _ in range(line_number):
            if not cursor.movePosition(QTextCursor.Down):
                return
        
        # 不選取，但放在該行開頭
        cursor.movePosition(QTextCursor.StartOfLine)
        cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)

        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor

        fmt = QTextCharFormat()
        fmt.setForeground(QColor("blue"))
        fmt.setBackground(Qt.transparent)  # 或 QColor("white") 視你背景而定
        selection.format = fmt

        # 設定新的 selection（只一筆）
        self.text_edit.setExtraSelections([selection])

        # 捲動到該行
        self.text_edit.setTextCursor(cursor)
    def on_scale_move(self, value): 
        self.frame_label.setText(f"Frame: {value}/{self.frame_slider.maximum()}")
        self.frame_label.adjustSize()
        scale = int(value)
        index = scale    
        w_vertices = self.cnc.workpiece_for_anime[index][0]
        w_faces = self.cnc.workpiece_for_anime[index][1]
        t_vertices = self.cnc.tool_for_anime[index][0]
        t_faces = self.cnc.tool_for_anime[index][1]
        
        if isinstance(self.cnc.cutting_parameters, list):
            result = np.concatenate(self.cnc.cutting_parameters, axis=0)
        else:
            result = self.cnc.cutting_parameters
        line_number = int(result[index, 8])
        self.highlight_line(line_number-1)

        if self.axvline1:
            self.axvline1.remove()
        if self.settings['2DPlot_Column_choose'][0] in (3, 4, 5, 6):
            self.axvline1 = self.ax1.axvline(x=self.STH_time[self.to_STH_index(index)], color='red')
        else:
            self.axvline1 = self.ax1.axvline(x=self.cnc.cutting_parameters[index, 9], color='red')
        self.canvas1.draw()
        
        if self.axvline2:
            self.axvline2.remove()
        if self.settings['2DPlot_Column_choose'][1] in (3, 4, 5, 6):
            self.axvline2 = self.ax2.axvline(x=self.STH_time[self.to_STH_index(index)], color='red')
        else:
            self.axvline2 = self.ax2.axvline(x=self.cnc.cutting_parameters[index, 9], color='red')
        self.canvas2.draw()
        
        self.plot_mesh(self.cnc.workpiece, self.cnc.tool,
                       w_vertices, w_faces, t_vertices, t_faces)

    def plot_mesh(self, workpiece, tool, w_vertices, w_faces, t_vertices, t_faces):
        # 更新 workpiece mesh
        mesh_pv = self.trimesh_to_pv(w_vertices, w_faces)
        
        if self.actor_workpiece:
            # 更新現有 mesh 的數據而非重新創建
            self.actor_workpiece.mapper.SetInputData(mesh_pv)
            self.actor_workpiece.mapper.Update()
        else:
            self.actor_workpiece = self.plotter_3d.add_mesh(mesh_pv, color='lightblue', show_edges=False)
        
        # 更新 tool mesh
        mesh_pv = self.trimesh_to_pv(t_vertices, t_faces)
        
        if self.actor_tool:
            # 更新現有 mesh 的數據而非重新創建
            self.actor_tool.mapper.SetInputData(mesh_pv)
            self.actor_tool.mapper.Update()
        else:
            self.actor_tool = self.plotter_3d.add_mesh(mesh_pv, color='lightblue', show_edges=False)

    def Calculate_thread(self):
        text = self.text_edit.toPlainText()
        self.settings['Gcode'] = text
        self.cnc.calculate_cutting_volume(self.settings['Simulation Mode'], self.progress_bar, self.settings['Workpiece'], self.settings['Tool'], self.settings['Workpiece Orientation'], self.settings['Workpiece Offset'], text.strip().split('\n'), self.settings['Controller'])
    def CalculateButton_Onclick(self):
        if self.check_filePath():
            self.set_Workpiece_Orientation()
            self.set_workpiece_offset()
            self.btn_simulate.setEnabled(False)
            self.frame_slider.setEnabled(False)
            self.progress_bar.setValue(0)
            if self.settings['Gcode'] != '':
                self.gcode_isPrepared = True
                
            self.cnc.simulation_step = self.settings['simulation_step']
            threading.Thread(target=self.Calculate_thread).start()
            
            threading.Thread(target=self.wait_for_plot_cutted_details).start()

    def wait_for_plot_cutted_details(self):
        while True:
            if self.progress_bar.value() >= 1000:
                self.frame_slider.setRange(0, len(self.cnc.workpiece_for_anime)-1)
                self.frame_slider.setEnabled(True)
                self.btn_simulate.setEnabled(True)
                break
            time.sleep(0.5)
            
        if isinstance(self.cnc.cutting_parameters, list):
            cutting_parameters = np.concatenate(self.cnc.cutting_parameters, axis=0)
        else:
            cutting_parameters = self.cnc.cutting_parameters
        
        if self.settings['2DPlot_Column_choose'][0] == 0 or self.settings['2DPlot_Column_choose'][0] == 1 or self.settings['2DPlot_Column_choose'][0] == 2:
            self.update_2d_plot1(cutting_parameters[:, 9], cutting_parameters[:, self.settings['2DPlot_Column_choose'][0]+5])
        elif self.settings['2DPlot_Column_choose'][0] in (3, 4, 5, 6):
            self.update_2d_plot1(self.create_STH_time_array(), self.STH_data[:, self.settings['2DPlot_Column_choose'][0]-3])
        elif self.settings['2DPlot_Column_choose'][0] == 7:
            self.update_2d_plot1(cutting_parameters[:, 9], cutting_parameters[:, 10])
            
        if self.settings['2DPlot_Column_choose'][1] == 0 or self.settings['2DPlot_Column_choose'][1] == 1 or self.settings['2DPlot_Column_choose'][1] == 2:
            self.update_2d_plot2(cutting_parameters[:, 9], cutting_parameters[:, self.settings['2DPlot_Column_choose'][1]+5])
        elif self.settings['2DPlot_Column_choose'][1] in (3, 4, 5, 6):
            self.update_2d_plot2(self.create_STH_time_array(), self.STH_data[:, self.settings['2DPlot_Column_choose'][1]-3])
        elif self.settings['2DPlot_Column_choose'][1] == 7:
            self.update_2d_plot2(cutting_parameters[:, 9], cutting_parameters[:, 10])
        
    def check_filePath(self):
        if not self.workpiece_isPrepared:
            QMessageBox.warning(self, '提示', '工件未匯入!')
            return False
        if not self.tool_isPrepared:
            QMessageBox.warning(self, '提示', '刀具未匯入!')
            return False
        if not self.Workpiece_Offset_isPrepared:
            QMessageBox.warning(self, '提示', 'Workpiece Offset未設定!')
            return False
        if not self.Workpiece_Orientation_isPrepared:
            QMessageBox.warning(self, '提示', 'Workpiece Orientation未設定!')
            return False
        if not self.gcode_isPrepared:
            QMessageBox.warning(self, '提示', 'Gcode未匯入!')
            return False
        if self.settings['Controller'] == '':
            QMessageBox.warning(self, '提示', '未選擇CController!')
            return False
        return True
        