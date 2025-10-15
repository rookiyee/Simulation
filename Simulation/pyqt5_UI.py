import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QTabWidget, 
                             QFrame, QSplitter, QScrollArea, QTreeWidget, 
                             QTreeWidgetItem, QMessageBox, QFileDialog,
                             QDialog, QLineEdit, QComboBox, QGridLayout, QFormLayout, QDialogButtonBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor, QCloseEvent
import os
from CAMWidget import SimulationWidget
from projectManager import ProjectManager
import pandas as pd
import numpy as np
import trimesh

class CAMSimulator(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CAM")
        self.setGeometry(100, 100, 1200, 800)
        self.setStyleSheet("background-color: #f0f0f0;")
        
        self.pj_manager = ProjectManager()
        self.project_counter = 1
        self.setup_ui()
        
    def setup_ui(self):
        # 主要中央控件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # 主佈局
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_widget.setLayout(main_layout)
        
        # 頂部工具列
        self.create_top_toolbar(main_layout)
        
        # 分頁控件
        self.notebook = QTabWidget()
        self.notebook.setTabsClosable(True)
        self.notebook.tabCloseRequested.connect(self.close_tab)
        main_layout.addWidget(self.notebook)
        
        # 建立第一個專案分頁
        self.create_new_project()
    
    def create_top_toolbar(self, parent_layout):
        """建立頂部橫向導引欄"""
        toolbar_frame = QFrame()
        toolbar_frame.setFixedHeight(50)
        toolbar_frame.setStyleSheet("background-color: #2c3e50;")
        
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_frame.setLayout(toolbar_layout)
        
        # 左側工具按鈕
        # 新增專案按鈕
        new_project_btn = QPushButton("New")
        new_project_btn.clicked.connect(self.create_new_project)
        new_project_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-family: Arial;
                font-size: 10pt;
                border: none;
                padding: 5px 15px;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        toolbar_layout.addWidget(new_project_btn)
        
        # 開啟專案按鈕
        import_btn = QPushButton("Open")
        import_btn.clicked.connect(self.load_project)
        import_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                font-family: Arial;
                font-size: 10pt;
                border: none;
                padding: 5px 15px;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #5dade2;
            }
        """)
        toolbar_layout.addWidget(import_btn)
        
        # 儲存專案按鈕
        save_all_btn = QPushButton("Save")
        save_all_btn.clicked.connect(self.save_current_projects)
        save_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #e67e22;
                color: white;
                font-family: Arial;
                font-size: 10pt;
                border: none;
                padding: 5px 15px;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #f39c12;
            }
        """)
        toolbar_layout.addWidget(save_all_btn)
        
        # 添加彈性空間
        toolbar_layout.addStretch()
        
        # 右側系統資訊
        system_label = QLabel("Simulation v1.0")
        system_label.setStyleSheet("""
            color: white;
            font-family: Arial;
            font-size: 10pt;
            margin: 10px;
        """)
        toolbar_layout.addWidget(system_label)
        
        parent_layout.addWidget(toolbar_frame)
    
    def create_new_project(self):
        """建立新的專案分頁"""
        project_name = f"Simulation {self.project_counter}"
        
        # 建立分頁控件
        tab_widget = QWidget()
        tab_widget.setStyleSheet("background-color: white;")
        
        # 建立專案內容
        self.create_project_content(tab_widget, project_name)
        
        # 添加到分頁控件
        tab_index = self.notebook.addTab(tab_widget, project_name)
        self.notebook.setCurrentIndex(tab_index)
        
        self.project_counter += 1
    
    def create_project_content(self, parent, project_name):
        """建立專案分頁的內容"""
        # 主容器佈局
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        parent.setLayout(main_layout)
        
        # 儲存當前分頁的組件引用
        tab_components = {
            'parent': parent,
            'sidebar_visible': True,
            'sidebar_frame': None,
            'main_content_frame': None,
            'toggle_button': None,
            'splitter': None
        }
        
        # 將組件資訊綁定到分頁
        parent.tab_components = tab_components
        
        # 建立可折疊的側邊欄和主內容區
        self.create_collapsible_layout(parent, project_name, tab_components, main_layout)
    
    def create_collapsible_layout(self, parent, project_name, tab_components, main_layout):
        """建立可折疊的側邊欄佈局"""
        # 使用 QSplitter 來實現可調整大小的面板
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setStyleSheet("QSplitter::handle { background-color: #bdc3c7; width: 2px; }")
        
        # 左側側邊欄容器
        sidebar_container = QWidget()
        sidebar_container.setStyleSheet("background-color: #34495e;")
        sidebar_container.setMinimumWidth(40)
        sidebar_container.setMaximumWidth(400)
        
        # 建立側邊欄內容
        sidebar_frame = self.create_left_sidebar_content(sidebar_container, project_name, tab_components)
        tab_components['sidebar_frame'] = sidebar_frame
        tab_components['sidebar_container'] = sidebar_container
        
        # 右側主要內容區域
        main_content_frame = SimulationWidget(main_splitter)
        main_content_frame.setMinimumWidth(400)
        tab_components['main_content_frame'] = main_content_frame
        
        # 將面板添加到 QSplitter
        main_splitter.addWidget(sidebar_container)
        main_splitter.addWidget(main_content_frame)
        
        # 設定初始大小比例
        main_splitter.setSizes([230, 970])
        
        # 儲存 QSplitter 引用
        tab_components['splitter'] = main_splitter
        
        main_layout.addWidget(main_splitter)
    
    def create_left_sidebar_content(self, parent, project_name, tab_components):
        """建立左側設定欄內容"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        parent.setLayout(main_layout)
        
        # 頂部切換按鈕區域
        toggle_frame = QFrame()
        toggle_frame.setFixedHeight(40)
        toggle_frame.setStyleSheet("background-color: #2c3e50;")
        
        toggle_layout = QHBoxLayout()
        toggle_layout.setContentsMargins(5, 5, 5, 5)
        toggle_frame.setLayout(toggle_layout)
        
        # 設定標題
        title_label = QLabel("System Setting")
        title_label.setStyleSheet("""
            color: white;
            font-family: Arial;
            font-size: 12pt;
            font-weight: bold;
        """)
        toggle_layout.addWidget(title_label)
        
        # 添加彈性空間
        toggle_layout.addStretch()
        
        # 折疊/展開按鈕 - 使用固定位置確保在右側
        toggle_btn = QPushButton("◀")
        toggle_btn.clicked.connect(lambda: self.toggle_sidebar(tab_components))
        toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #34495e;
                color: white;
                font-family: Arial;
                font-size: 12pt;
                font-weight: bold;
                border: none;
                min-width: 30px;
                max-width: 30px;
                min-height: 30px;
                max-height: 30px;
            }
            QPushButton:hover {
                background-color: #5d6d7e;
            }
        """)
        toggle_btn.setFixedSize(30, 30)
        toggle_btn.setCursor(Qt.PointingHandCursor)
        toggle_layout.addWidget(toggle_btn, 0, Qt.AlignRight)
        
        main_layout.addWidget(toggle_frame)
        
        # 設定內容區域 - 使用滾動區域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #34495e;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #2c3e50;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background-color: #5d6d7e;
                border-radius: 5px;
            }
        """)
        
        # 滾動內容控件
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: #34495e;")
        
        # 水平佈局容納樹狀控件和詳細設定區域
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(5, 5, 5, 5)
        scroll_content.setLayout(content_layout)
        
        # 建立樹狀控件
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color: #2c3e50;
                color: white;
                border: none;
                font-family: Arial;
                font-size: 10pt;
            }
            QTreeWidget::item {
                height: 25px;
                border-bottom: 1px solid #34495e;
            }
            QTreeWidget::item:selected {
                background-color: #3498db;
            }
            QTreeWidget::item:hover {
                background-color: #34495e;
            }
            # QTreeWidget::branch:has-children:!has-siblings:closed,
            # QTreeWidget::branch:closed:has-children:has-siblings {
            #     border-image: none;
            #     image: url(none);
            # }
            # QTreeWidget::branch:open:has-children:!has-siblings,
            # QTreeWidget::branch:open:has-children:has-siblings {
            #     border-image: none;
            #     image: url(none);
            # }
        """)
        
        # 添加樹狀項目        
        import_data_item = QTreeWidgetItem(['Import File'])
        import_data_item.setExpanded(True)
        import_data_item.addChild(QTreeWidgetItem(['Quick Create 3D model']))
        import_data_item.addChild(QTreeWidgetItem(['Workpiece']))
        import_data_item.addChild(QTreeWidgetItem(['Tool']))
        import_data_item.addChild(QTreeWidgetItem(['Gcode']))
        import_data_item.addChild(QTreeWidgetItem(['STH Signal']))
        self.tree.addTopLevelItem(import_data_item)
        
        export_item = QTreeWidgetItem(['Export Data'])
        export_item.setExpanded(True)
        export_item.addChild(QTreeWidgetItem(['Synchronized STH data']))
        self.tree.addTopLevelItem(export_item)
        
        cam_item = QTreeWidgetItem(['Simulation Setting'])
        cam_item.setExpanded(True)
        cam_item.addChild(QTreeWidgetItem(['Workpiece Offset']))
        cam_item.addChild(QTreeWidgetItem(['Workpiece Orientation']))
        cam_item.addChild(QTreeWidgetItem(['Simulation Step']))
        cam_item.addChild(QTreeWidgetItem(['Simulation Mode']))
        self.tree.addTopLevelItem(cam_item)
        
        Plot2D_item = QTreeWidgetItem(['2D Plotting Setting'])
        Plot2D_item.setExpanded(True)
        Plot2D_item.addChild(QTreeWidgetItem(['Plotting Content']))
        self.tree.addTopLevelItem(Plot2D_item)
        
        # 連接樹狀控件選擇事件
        self.tree.itemClicked.connect(self.on_tree_select)
        
        content_layout.addWidget(self.tree)
        
        # 設定詳細區域
        self.setting_detail_frame = QWidget()
        self.setting_detail_frame.setStyleSheet("background-color: #34495e;")
        content_layout.addWidget(self.setting_detail_frame)
        
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # 儲存按鈕引用以便後續控制
        tab_components['toggle_button'] = toggle_btn
        tab_components['title_label'] = title_label
        tab_components['scroll_area'] = scroll_area
        
        return parent
    
    def toggle_sidebar(self, tab_components):
        """切換側邊欄顯示/隱藏"""
        sidebar_container = tab_components['sidebar_container']
        toggle_btn = tab_components['toggle_button']
        title_label = tab_components['title_label']
        
        if tab_components['sidebar_visible']:
            # 隱藏側邊欄
            sidebar_container.setMaximumWidth(40)
            sidebar_container.setMinimumWidth(40)
            toggle_btn.setText("▶")
            # 隱藏標題和內容區域
            title_label.hide()
            scroll_area = tab_components['scroll_area']
            scroll_area.hide()
            tab_components['sidebar_visible'] = False
        else:
            # 顯示側邊欄
            sidebar_container.setMaximumWidth(400)
            sidebar_container.setMinimumWidth(200)
            toggle_btn.setText("◀")
            # 顯示標題和內容
            title_label.show()
            scroll_area = tab_components['scroll_area']
            scroll_area.show()
            tab_components['sidebar_visible'] = True
    
    def window_input_filePath(self, frameClass, key):
        class InputFileDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle(key)
                self.setFixedSize(300, 200)
                self.settings_dict = frameClass.settings
    
                layout = QVBoxLayout()
    
                label = QLabel(key)
                label.setStyleSheet("font-size: 14px;")
                layout.addWidget(label)
    
                self.entry = QLineEdit()
                self.entry.setText(self.settings_dict.get(key, ""))
                layout.addWidget(self.entry)
    
                select_btn = QPushButton("Select File")
                select_btn.setStyleSheet("background-color: #27ae60; color: white;")
                select_btn.clicked.connect(self.select_file)
                layout.addWidget(select_btn)
    
                apply_btn = QPushButton("Apply")
                apply_btn.setStyleSheet("background-color: #27ae60; color: white;")
                apply_btn.clicked.connect(self.apply_changes)
                layout.addWidget(apply_btn)
    
                self.setLayout(layout)
    
            def select_file(self):
                if key == 'STH Signal':
                    file_path, _ = QFileDialog.getOpenFileName(
                        self, "Select File", "", " CSV files (*.csv);;所有檔案 (*)"
                    )
                else:
                    file_path, _ = QFileDialog.getOpenFileName(
                        self, "Select File", "", "STL files (*.stl);;所有檔案 (*)"
                    )
                if file_path:
                    self.entry.setText(os.path.abspath(file_path))
    
            def apply_changes(self):
                self.settings_dict[key] = self.entry.text()
                if key == 'Workpiece':
                    frameClass.import_workpiece()
                elif key == 'Tool':
                    frameClass.import_tool()
                elif key == 'STH Signal':
                    frameClass.import_STH_data()
                self.accept()
    
        dialog = InputFileDialog(self)
        dialog.exec_()
    
    def open_window_for_workpiece_offset(self, frameClass):
        class OffsetDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle("Workpiece Offset")
                self.setFixedSize(300, 200)
    
                offset = frameClass.settings['Workpiece Offset']
                self.entries = {}
    
                grid = QGridLayout()
                axes = ['X', 'Y', 'Z']
                for i, axis in enumerate(axes):
                    label = QLabel(axis)
                    entry = QLineEdit()
                    entry.setText(str(offset[i]))
                    grid.addWidget(label, i, 0)
                    grid.addWidget(entry, i, 1)
                    self.entries[axis] = entry
    
                # Apply 按鈕
                apply_btn = QPushButton("Apply")
                apply_btn.setStyleSheet("background-color: #27ae60; color: white;")
                apply_btn.clicked.connect(self.apply_values)
                grid.addWidget(apply_btn, 3, 0, 1, 2)
    
                # 置中整個 layout
                layout = QVBoxLayout()
                layout.addLayout(grid)
                self.setLayout(layout)
    
            def apply_values(self):
                x = self.entries['X'].text()
                y = self.entries['Y'].text()
                z = self.entries['Z'].text()
    
                if not x:
                    QMessageBox.warning(self, "Warning", "Please enter X offset!")
                    return
                elif not y:
                    QMessageBox.warning(self, "Warning", "Please enter Y offset!")
                    return
                elif not z:
                    QMessageBox.warning(self, "Warning", "Please enter Z offset!")
                    return
    
                try:
                    values = [float(x), float(y), float(z)]
                except ValueError:
                    QMessageBox.warning(self, "Warning", "Please enter the valid number！")
                    return
    
                frameClass.settings['Workpiece Offset'] = values
                if frameClass.set_workpiece_offset():
                    frameClass.plot_tool_mesh()
                self.accept()
    
        dialog = OffsetDialog(self)
        dialog.exec_()
            
    def open_window_for_gcode(self, frameClass):
        class GcodeDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle("Gcode")
                self.setFixedSize(350, 220)
    
                self.main_layout = QVBoxLayout()
                self.setLayout(self.main_layout)
    
                # 標籤 + 下拉選單
                label = QLabel("Please select data source：")
                self.combo = QComboBox()
                self.combo.addItems(["Import files from your computer", "Connect to the CNC to obtain data"])
                self.combo.currentIndexChanged.connect(self.on_combo_change)
                self.combo.setStyleSheet("""
                    QComboBox {
                        padding: 5px;
                        font-size: 14px;
                    }
                    QComboBox QAbstractItemView {
                        selection-background-color: white;
                        selection-color: black;
                    }
                """)
    
                self.main_layout.addWidget(label)
                self.main_layout.addWidget(self.combo)
                
                label2 = QLabel("Please select Controller：")
                self.combo2 = QComboBox()
                self.combo2.addItems(["Siemens", "Fanuc"])
                self.combo2.currentIndexChanged.connect(self.on_combo_change)
                self.combo2.setStyleSheet("""
                    QComboBox {
                        padding: 5px;
                        font-size: 14px;
                    }
                    QComboBox QAbstractItemView {
                        selection-background-color: white;
                        selection-color: black;
                    }
                """)
    
                self.main_layout.addWidget(label2)
                self.main_layout.addWidget(self.combo2)
    
                # 動態元件區域
                self.dynamic_frame = QWidget()
                self.dynamic_layout = QVBoxLayout()
                self.dynamic_frame.setLayout(self.dynamic_layout)
                self.main_layout.addWidget(self.dynamic_frame)
                
                # ✅ 預設顯示第一個選項對應畫面
                self.combo.setCurrentIndex(0)
                self.on_combo_change(0)
    
            def clear_dynamic_frame(self):
                while self.dynamic_layout.count():
                    item = self.dynamic_layout.takeAt(0)
                    widget = item.widget()
                    if widget:
                        widget.deleteLater()
    
            def on_combo_change(self, index):
                self.clear_dynamic_frame()
                selected = self.combo.currentText()
    
                if selected == "Import files from your computer":
                    self.file_path_edit = QLineEdit()
                    self.file_path_edit.setPlaceholderText("")
                    self.file_path_edit.setAlignment(Qt.AlignCenter)
    
                    browse_btn = QPushButton("Select File")
                    browse_btn.clicked.connect(self.browse_file)
    
                    apply_btn = QPushButton("Apply")
                    apply_btn.clicked.connect(self.apply_file)
    
                    self.dynamic_layout.addWidget(self.file_path_edit)
                    self.dynamic_layout.addWidget(browse_btn)
                    self.dynamic_layout.addWidget(apply_btn)
    
                elif selected == "Connect to the CNC to obtain data":
                    connect_btn = QPushButton("Conect")
                    connect_btn.clicked.connect(self.connect_machine)
    
                    apply_btn = QPushButton("Apply")
                    apply_btn.clicked.connect(self.apply_machine)
    
                    self.dynamic_layout.addWidget(connect_btn)
                    self.dynamic_layout.addWidget(apply_btn)
    
            def browse_file(self):
                path, _ = QFileDialog.getOpenFileName(self, "Select G-code file", "", "G-code files (*.nc *.mpf *.txt);;所有檔案 (*)")
                if path:
                    self.file_path_edit.setText(path)
    
            def apply_file(self):
                path = self.file_path_edit.text()
                if path:
                    frameClass.display_gcode(path, True)
                    frameClass.settings['Controller'] = self.combo2.currentText()
                    self.accept()
                else:
                    QMessageBox.warning(self, "Warning", "Please select the file first！")
    
            def connect_machine(self):
                QMessageBox.information(self, "Message", "Connection successful")
    
            def apply_machine(self):
                frameClass.connect_cnc()
                self.accept()
    
        # 建立並執行 dialog
        dialog = GcodeDialog(self)
        dialog.exec_()

    def open_window_for_workpiece_rotation(self, frameClass):
        class RotationDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle("Axis Setting")
                self.setFixedSize(400, 280)
    
                setting = frameClass.settings['Workpiece Orientation']
                options = ["First C-axis, then A-axis", "First A-axis, then C-axis"]
    
                layout = QGridLayout()
                self.setLayout(layout)
    
                # 1. Combobox 選擇旋轉順序
                layout.addWidget(QLabel("Select rotation order："), 0, 0, 1, 1, Qt.AlignRight)
                self.rotation_order_combo = QComboBox()
                self.rotation_order_combo.addItems(options)
                self.rotation_order_combo.setStyleSheet("""
                    QComboBox {
                        padding: 5px;
                        font-size: 14px;
                    }
                    QComboBox QAbstractItemView {
                        selection-background-color: white;
                        selection-color: black;
                    }
                """)
                # 根據設定預設選項
                if setting[2] == 1:
                    self.rotation_order_combo.setCurrentIndex(0)
                elif setting[2] == 0:
                    self.rotation_order_combo.setCurrentIndex(1)
                layout.addWidget(self.rotation_order_combo, 0, 1, 1, 3)
    
                # 2. C軸角度
                layout.addWidget(QLabel("C-axis angle："), 1, 0, Qt.AlignRight)
                self.c_angle_edit = QLineEdit(str(setting[0]))
                layout.addWidget(self.c_angle_edit, 1, 1, 1, 3)
    
                # 3. A軸角度
                layout.addWidget(QLabel("A-axis angle："), 2, 0, Qt.AlignRight)
                self.a_angle_edit = QLineEdit(str(setting[1]))
                layout.addWidget(self.a_angle_edit, 2, 1, 1, 3)
    
                # 4. C軸旋轉中心點 (3個輸入框)
                layout.addWidget(QLabel("C-axis rotation center point："), 3, 0, Qt.AlignRight)
                self.c_center_edits = []
                for i in range(3):
                    le = QLineEdit(str(setting[3][i]))
                    le.setFixedWidth(70)
                    le.setAlignment(Qt.AlignCenter)
                    layout.addWidget(le, 3, 1 + i)
                    self.c_center_edits.append(le)
    
                # 5. A軸旋轉中心點 (3個輸入框)
                layout.addWidget(QLabel("A-axis rotation center point："), 4, 0, Qt.AlignRight)
                self.a_center_edits = []
                for i in range(3):
                    le = QLineEdit(str(setting[4][i]))
                    le.setFixedWidth(70)
                    le.setAlignment(Qt.AlignCenter)
                    layout.addWidget(le, 4, 1 + i)
                    self.a_center_edits.append(le)
    
                # 6. Apply 按鈕
                apply_btn = QPushButton("Apply")
                apply_btn.clicked.connect(self.on_apply)
                layout.addWidget(apply_btn, 5, 0, 1, 4)
    
            def on_apply(self):
                order_index = self.rotation_order_combo.currentIndex()
                c_angle = self.c_angle_edit.text()
                a_angle = self.a_angle_edit.text()
                c_center = [le.text() for le in self.c_center_edits]
                a_center = [le.text() for le in self.a_center_edits]
    
                # 驗證
                if c_angle == '':
                    QMessageBox.warning(self, '提示', 'Please enter C offset!')
                    return
                if a_angle == '':
                    QMessageBox.warning(self, '提示', 'Please enter A offset!')
                    return
                if order_index not in (0,1):
                    QMessageBox.warning(self, '提示', 'Please choose rotation order!')
                    return
                if '' in c_center:
                    QMessageBox.warning(self, '提示', 'Please enter C axis rotation center!')
                    return
                if '' in a_center:
                    QMessageBox.warning(self, '提示', 'Please enter A axis rotation center!')
                    return
    
                try:
                    c_angle_f = float(c_angle)
                    a_angle_f = float(a_angle)
                    c_center_f = [float(v) for v in c_center]
                    a_center_f = [float(v) for v in a_center]
                except ValueError:
                    QMessageBox.warning(self, '錯誤', 'Please enter valid number！')
                    return
    
                # rotation_order: options[0] index=0 => 1, options[1] index=1 => 0 （和你原本對應）
                order = 1 if order_index == 0 else 0
    
                frameClass.settings['Workpiece Orientation'] = [c_angle_f, a_angle_f, order, c_center_f, a_center_f]
                if frameClass.set_Workpiece_Orientation():
                    frameClass.plot_workpiece_mesh()
                self.accept()
    
        dialog = RotationDialog(self)
        dialog.exec_()
        
    def open_window_for_PlotContent(self, frameClass):
        class SelectionDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle("Select Plotting Content")
                self.setFixedSize(350, 280)
                self.setModal(False)  # 不阻塞主視窗互動
        
                layout = QVBoxLayout()
                
                # 標籤與下拉選單1
                layout.addWidget(QLabel("Select left view"))
                self.combo1 = QComboBox()
                self.combo1.setStyleSheet("""
                    QComboBox {
                        padding: 5px;
                        font-size: 14px;
                    }
                    QComboBox QAbstractItemView {
                        selection-background-color: white;
                        selection-color: black;
                    }
                """)
                self.combo1.addItems(["Radial Cutting Depth", "Axial Cutting Depth", "切削截面積", "STH Signal CH1", "STH Signal CH2", "STH Signal CH3", "STH Signal CH4", "模擬的切削力"])
                self.combo1.setCurrentIndex(frameClass.settings['2DPlot_Column_choose'][0])
                layout.addWidget(self.combo1)
        
                # 標籤與下拉選單2
                layout.addWidget(QLabel("Select right view"))
                self.combo2 = QComboBox()
                self.combo2.setStyleSheet("""
                    QComboBox {
                        padding: 5px;
                        font-size: 14px;
                    }
                    QComboBox QAbstractItemView {
                        selection-background-color: white;
                        selection-color: black;
                    }
                """)
                self.combo2.addItems(["Radial Cutting Depth", "Axial Cutting Depth", "切削截面積", "STH Signal CH1", "STH Signal CH2", "STH Signal CH3", "STH Signal CH4", "模擬的切削力"])
                self.combo2.setCurrentIndex(frameClass.settings['2DPlot_Column_choose'][1])
                layout.addWidget(self.combo2)
        
                # Apply 按鈕
                self.apply_button = QPushButton("Apply")
                self.apply_button.clicked.connect(self.apply_selection)
                layout.addWidget(self.apply_button)
        
                self.setLayout(layout)
        
            def apply_selection(self):
                selected_option1 = self.combo1.currentIndex()
                selected_option2 = self.combo2.currentIndex()
                frameClass.settings['2DPlot_Column_choose'][0] = selected_option1
                frameClass.settings['2DPlot_Column_choose'][1] = selected_option2
                if list(frameClass.cnc.cutting_parameters) != []:
                    if selected_option1 in (0, 1, 2):
                        frameClass.update_2d_plot1(frameClass.cnc.cutting_parameters[:, 9], frameClass.cnc.cutting_parameters[:, frameClass.settings['2DPlot_Column_choose'][0]+5])
                    elif selected_option1 in (3, 4, 5, 6):
                        frameClass.update_2d_plot1(frameClass.create_STH_time_array(), frameClass.STH_data[:, selected_option1-3])
                    elif  selected_option1 == 7:
                        frameClass.update_2d_plot1(frameClass.cnc.cutting_parameters[:, 9], frameClass.cnc.cutting_parameters[:, 10])
                        
                    if selected_option2 in (0, 1, 2):
                        frameClass.update_2d_plot2(frameClass.cnc.cutting_parameters[:, 9], frameClass.cnc.cutting_parameters[:, frameClass.settings['2DPlot_Column_choose'][1]+5])
                    elif selected_option2 in (3, 4, 5, 6):
                        frameClass.update_2d_plot2(frameClass.create_STH_time_array(), frameClass.STH_data[:, selected_option2-3])
                    elif  selected_option2 == 7:
                        frameClass.update_2d_plot2(frameClass.cnc.cutting_parameters[:, 9], frameClass.cnc.cutting_parameters[:, 10])
                        
                self.accept()  # 關閉對話框
        dialog = SelectionDialog(self)
        dialog.exec_()
    
    def open_window_for_simulation_step(self, frameClass):
        class InputDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle("輸入參數")
                self.setFixedSize(350, 280)
        
                # 主 layout
                layout = QVBoxLayout()
        
                # 輸入區（輸入框 + mm）
                input_layout = QHBoxLayout()
                self.input_edit = QLineEdit()
                self.input_edit.setText(str(frameClass.settings['simulation_step']))
                input_layout.addWidget(self.input_edit)
                input_layout.addWidget(QLabel("mm"))
                layout.addLayout(input_layout)
                frameClass.settings['simulation_step']
        
                # Apply 按鈕
                self.apply_btn = QPushButton("Apply")
                self.apply_btn.clicked.connect(self.apply_and_close)
                layout.addWidget(self.apply_btn)
        
                self.setLayout(layout)
        
            def apply_and_close(self):
                frameClass.settings['simulation_step'] = float(self.input_edit.text())
                self.accept()  # 關閉視窗
        dialog = InputDialog(self)
        dialog.exec_()
        
    def open_window_for_simulation_mode(self, frameClass):
        class InputDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle("選擇模擬模式")
                self.setFixedSize(350, 180)
    
                # 主 layout
                layout = QVBoxLayout()
    
                # 下拉選單
                input_layout = QHBoxLayout()
                self.combo_box = QComboBox()
                self.combo_box.addItems(["Simplified", "Accurate"])
    
                # 根據原本設定值選擇對應的選項
                current_value = frameClass.settings.get('Simulation Mode', "Simplified")
                index = self.combo_box.findText(str(current_value))
                if index >= 0:
                    self.combo_box.setCurrentIndex(index)
    
                input_layout.addWidget(QLabel("Simulation Mode:"))
                input_layout.addWidget(self.combo_box)
                layout.addLayout(input_layout)
    
                # Apply 按鈕
                self.apply_btn = QPushButton("Apply")
                self.apply_btn.clicked.connect(self.apply_and_close)
                layout.addWidget(self.apply_btn)
    
                self.setLayout(layout)
    
            def apply_and_close(self):
                frameClass.settings['Simulation Mode'] = self.combo_box.currentText()
                self.accept()  # 關閉視窗
    
        dialog = InputDialog(self)
        dialog.exec_()

    def open_window_for_Synchronized_STH_data(self, frameClass):
        class InputDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
        
                self.setWindowTitle("輸入起始與結束點")
                self.setFixedSize(300, 150)
        
                layout = QVBoxLayout()
        
                # 起始點
                start_layout = QHBoxLayout()
                start_label = QLabel("Start point on the Frame:")
                self.start_edit = QLineEdit()
                self.start_edit.setText(str(frameClass.settings['STH data Synchronized range'][0]))
                start_layout.addWidget(start_label)
                start_layout.addWidget(self.start_edit)
                layout.addLayout(start_layout)
        
                # 結束點
                end_layout = QHBoxLayout()
                end_label = QLabel("End point on the Frame:")
                self.end_edit = QLineEdit()
                self.end_edit.setText(str(frameClass.settings['STH data Synchronized range'][1]))
                end_layout.addWidget(end_label)
                end_layout.addWidget(self.end_edit)
                layout.addLayout(end_layout)
        
                # 按鈕
                self.apply_button = QPushButton("Export")
                self.apply_button.clicked.connect(self.export_and_close)
                layout.addWidget(self.apply_button)
        
                self.setLayout(layout)
                
            def export_and_close(self):
                frameClass.settings['STH data Synchronized range'] = [float(self.start_edit.text()), float(self.end_edit.text())]
                frameClass.synchronize_STH_signal()
                self.accept()  # 關閉視窗

        dialog = InputDialog(self)
        dialog.exec_()

    def open_window_for_create_3dModel(self):
        class InputDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle("建立 3D 模型")
                self.setFixedSize(300, 150)
                layout = QVBoxLayout()
    
                # 下拉選單: 選擇形狀
                self.shape_combo = QComboBox()
                self.shape_combo.addItems(["長方體", "圓柱體"])
                layout.addWidget(QLabel("選擇形狀:"))
                layout.addWidget(self.shape_combo)
    
                # 輸入欄位
                self.form_layout = QFormLayout()
                self.entry1 = QLineEdit()
                self.entry2 = QLineEdit()
                self.entry3 = QLineEdit()
    
                self.form_layout.addRow("長 (X):", self.entry1)
                self.form_layout.addRow("寬 (Y):", self.entry2)
                self.form_layout.addRow("高 (Z):", self.entry3)
    
                layout.addLayout(self.form_layout)
    
                # 按鈕
                buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
                buttons.accepted.connect(self.generate_stl)
                buttons.rejected.connect(self.reject)
                layout.addWidget(buttons)
    
                self.setLayout(layout)
    
                # 初始狀態
                self.shape_combo.currentIndexChanged.connect(self.update_fields)
                self.update_fields(0)
    
            def update_fields(self, index):
                """依形狀切換輸入欄位"""
                if index == 0:  # 長方體
                    self.form_layout.labelForField(self.entry1).setText("長 (X):")
                    self.form_layout.labelForField(self.entry2).setText("寬 (Y):")
                    self.form_layout.labelForField(self.entry3).setText("高 (Z):")
                    self.entry2.show()
                else:  # 圓柱體
                    self.form_layout.labelForField(self.entry1).setText("半徑:")
                    self.form_layout.labelForField(self.entry2).setText("")  # 不需要
                    self.form_layout.labelForField(self.entry3).setText("高 (Z):")
                    self.entry2.hide()
    
            def generate_stl(self):
                try:
                    shape = self.shape_combo.currentText()
    
                    # 選擇存檔路徑
                    filename, _ = QFileDialog.getSaveFileName(
                        self, "選擇儲存位置", "", "STL 檔案 (*.stl)"
                    )
                    if not filename:  # 使用者取消
                        return
    
                    if shape == "長方體":
                        length = float(self.entry1.text())
                        width = float(self.entry2.text())
                        height = float(self.entry3.text())
                        self.create_box_stl(length, width, height, filename)
                    else:
                        radius = float(self.entry1.text())
                        height = float(self.entry3.text())
                        self.create_cylinder_stl(radius, height, filename)
    
                    QMessageBox.information(self, "成功", f"STL 檔案已產生！\n{filename}")
                    self.accept()
    
                except ValueError:
                    QMessageBox.critical(self, "錯誤", "請輸入正確的數值！")
            def create_box_stl(self, length, width, height, filename):
                box = trimesh.creation.box(extents=[length, width, height])
                box.export(filename)

            def create_cylinder_stl(self, radius, height, filename):
                cylinder = trimesh.creation.cylinder(radius=radius, height=height, sections=64)
                cylinder.export(filename)

        dialog = InputDialog(self)
        dialog.exec_()
        
    def on_tree_select(self, item, column):
        item_text = item.text(0)

        # 跳過非葉節點：這裡簡單處理，實際可依層級判斷
        if item.childCount() > 0:
            return

        current_tab = self.notebook.currentWidget()
        if not hasattr(current_tab, 'tab_components'):
            return

        tab_components = current_tab.tab_components
        main_frame = tab_components['main_content_frame']

        if item_text in ['Workpiece', 'Tool']:
            self.window_input_filePath(main_frame, item_text)
        elif item_text == 'Quick Create 3D model':
            self.open_window_for_create_3dModel()
        elif item_text == 'Gcode':
            self.open_window_for_gcode(main_frame)
        elif item_text == 'STH Signal':
            self.window_input_filePath(main_frame, item_text)
        elif item_text == 'Workpiece Offset':
            self.open_window_for_workpiece_offset(main_frame)
        elif item_text == 'Workpiece Orientation':
            self.open_window_for_workpiece_rotation(main_frame)
        elif item_text == 'Plotting Content':
            self.open_window_for_PlotContent(main_frame)
        elif item_text == 'Simulation Step':
            self.open_window_for_simulation_step(main_frame)
        elif item_text == 'Simulation Mode':
            self.open_window_for_simulation_mode(main_frame)
        elif item_text == 'Synchronized STH data':
            if main_frame.settings['STH Signal'] == '' or not main_frame.frame_slider.isEnabled():
                QMessageBox.information(self, "Warning", "Please import STH Signal first or simulate first!")
            else:
                self.open_window_for_Synchronized_STH_data(main_frame)
            

    
    def close_tab(self, index):
        """關閉指定的分頁"""
        current_tab_widget = self.notebook.currentWidget()
        current_tab_widget.tab_components['main_content_frame'].plotter_3d.close()
        current_tab_widget.tab_components['main_content_frame'].plotter_3d.deep_clean()
        del current_tab_widget.tab_components['main_content_frame'].plotter_3d
        
        self.notebook.removeTab(index)
    
    def ready(self):
        current_tab_widget = self.notebook.currentWidget()

        tab_components = current_tab_widget.tab_components
        frameClass = tab_components['main_content_frame']
        frameClass.import_workpiece()
        frameClass.import_tool()
        frameClass.import_STH_data()
        frameClass.display_gcode()
        if frameClass.set_workpiece_offset():
            frameClass.plot_tool_mesh()
        if frameClass.set_Workpiece_Orientation():
            frameClass.plot_workpiece_mesh()
            
        if frameClass.settings['workpiece_for_anime'] != '' and frameClass.settings['tool_for_anime'] != '':
            frameClass.cnc.workpiece_for_anime = np.load(frameClass.settings['workpiece_for_anime'], allow_pickle=True)['data']
            frameClass.cnc.tool_for_anime = np.load(frameClass.settings['tool_for_anime'], allow_pickle=True)['data']
            frameClass.frame_slider.setRange(0, len(frameClass.cnc.tool_for_anime)-1)
            frameClass.frame_slider.setEnabled(True)
            frameClass.btn_simulate.setEnabled(True)
        if frameClass.settings['All Cutting Parameters'] != '':
            data = pd.read_csv(frameClass.settings['All Cutting Parameters'], skiprows=1, header=None)
            data = np.array(data)
            frameClass.cnc.cutting_parameters = data
            frameClass.cnc.initial_CuttingPara_query()
            
            selected_option1 = frameClass.settings['2DPlot_Column_choose'][0]
            selected_option2 = frameClass.settings['2DPlot_Column_choose'][1]
            if selected_option1 in (0, 1, 2):
                frameClass.update_2d_plot1(frameClass.cnc.cutting_parameters[:, 9], frameClass.cnc.cutting_parameters[:, frameClass.settings['2DPlot_Column_choose'][0]+5])
            elif selected_option1 in (3, 4, 5, 6):
                frameClass.update_2d_plot1(frameClass.create_STH_time_array(), frameClass.STH_data[:, selected_option1-3])
            elif  selected_option1 == 7:
                frameClass.update_2d_plot1(frameClass.cnc.cutting_parameters[:, 9], frameClass.cnc.cutting_parameters[:, 10])
                
            if selected_option2 in (0, 1, 2):
                frameClass.update_2d_plot2(frameClass.cnc.cutting_parameters[:, 9], frameClass.cnc.cutting_parameters[:, frameClass.settings['2DPlot_Column_choose'][1]+5])
            elif selected_option2 in (3, 4, 5, 6):
                frameClass.update_2d_plot2(frameClass.create_STH_time_array(), frameClass.STH_data[:, selected_option1-3])
            elif  selected_option2 == 7:
                frameClass.update_2d_plot2(frameClass.cnc.cutting_parameters[:, 9], frameClass.cnc.cutting_parameters[:, 10])
                
    def load_project(self):   
        loading_dialog = QDialog(self)
        tuple_data = self.pj_manager.load_project(loading_dialog)
        if tuple_data:
            filename = tuple_data[0]
            setting = tuple_data[1]
            self.create_new_project()
            
            current_tab_widget = self.notebook.currentWidget()
            tab_components = current_tab_widget.tab_components
            current_index = self.notebook.currentIndex()
            self.notebook.setTabText(current_index, filename)
            tab_components['main_content_frame'].settings = setting
            self.ready()
        loading_dialog.accept()  # 關閉視窗
    
    def save_current_projects(self):
        current_tab_widget = self.notebook.currentWidget()

        tab_components = current_tab_widget.tab_components
        filename = self.pj_manager.save_project(tab_components['main_content_frame'], current_tab_widget)
        # filename = self.pj_manager.save_project(tab_components['main_content_frame'])
        if filename:
            current_index = self.notebook.currentIndex()
            self.notebook.setTabText(current_index, filename)

        
    def closeEvent(self, event: QCloseEvent):
        # reply = QMessageBox.question(
        #     self, 
        #     '確認',
        #     "您確定要關閉視窗嗎？", 
        #     QMessageBox.Yes | QMessageBox.No, 
        #     QMessageBox.No
        # )
        
        # if reply == QMessageBox.Yes:
        #     tab_count = self.notebook.count()
        #     all_tabs = [self.notebook.widget(i) for i in range(tab_count)]
        #     for tab in all_tabs:
        #         tab.tab_components['main_content_frame'].plotter_3d.close()
        #         tab.tab_components['main_content_frame'].plotter_3d.deep_clean()
        #         del tab.tab_components['main_content_frame'].plotter_3d     
        #     # 接受關閉事件，視窗將會被銷毀
        #     event.accept() 
        # else:
        #     # 忽略關閉事件，視窗將保持開啟
        #     event.ignore()
        
        tab_count = self.notebook.count()
        all_tabs = [self.notebook.widget(i) for i in range(tab_count)]
        for tab in all_tabs:
            tab.tab_components['main_content_frame'].plotter_3d.close()
            tab.tab_components['main_content_frame'].plotter_3d.deep_clean()
            del tab.tab_components['main_content_frame'].plotter_3d     
        # 接受關閉事件，視窗將會被銷毀
        event.accept() 
            
def main():
    app = QApplication(sys.argv)
    
    # 設定應用程式樣式
    app.setStyle('Fusion')
    
    # 設定深色主題（可選）
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(240, 240, 240))
    palette.setColor(QPalette.WindowText, Qt.black)
    app.setPalette(palette)
    
    # 建立並顯示主視窗
    window = CAMSimulator()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()