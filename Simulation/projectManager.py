import json
import os
import sys
from datetime import datetime
import shutil
import numpy as np
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QDialog, QLabel, QVBoxLayout

class ProjectManager:
    def __init__(self, default_extension=".camproj"):
        """
        專案管理器
        
        Args:
            default_extension (str): 預設的專案檔案副檔名
        """
        self.default_extension = default_extension
        self.file_types = [
            ("CAM專案", f"*{default_extension}"),
            ("JSON檔案", "*.json"),
            ("所有檔案", "*.*")
        ]
        
    def get_base_path(self):
        if getattr(sys, 'frozen', False):  # 如果是打包成 EXE
            base_path = os.path.dirname(sys.executable)  # EXE 所在資料夾
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))  # 開發模式：.py 檔所在資料夾
        return base_path
    def save_project(self, frameClass, parent=None, default_filename="新專案"):
        try:
            settings_dict = frameClass.settings
            project_data = {
                "metadata": {
                    "version": "1.0",
                    "created_time": datetime.now().isoformat(),
                    "app_name": "My Application",
                },
                "settings": settings_dict
            }

            file_path, _ = QFileDialog.getSaveFileName(
                parent,
                "儲存專案",
                f"{default_filename}{self.default_extension}",
                "CAM專案 (*.camproj);;JSON檔案 (*.json);;所有檔案 (*)"
            )

            if not file_path:
                return None

            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            # === 顯示「儲存中」對話框，阻止使用者操作 ===
            waiting_dialog = QDialog(parent)
            waiting_dialog.setModal(True)
            waiting_dialog.setWindowTitle("儲存中")
            waiting_dialog.setWindowFlags(waiting_dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
            layout = QVBoxLayout()
            label = QLabel("正在儲存專案，請稍候...")
            layout.addWidget(label)
            waiting_dialog.setLayout(layout)
            waiting_dialog.setFixedSize(250, 100)
            waiting_dialog.show()
            QApplication.processEvents()  # 強制顯示視窗

            # === 儲存CSV副檔案 ===
            base_path = self.get_base_path()
            source_csv_path = os.path.join(base_path, "TemporarySaved", "data", "all_cutting_parameters.csv")
            target_csv_path = os.path.splitext(file_path)[0] + "_PartGeometry.csv"
            if os.path.exists(source_csv_path):
                shutil.copyfile(source_csv_path, target_csv_path)
            else:
                QMessageBox.warning(parent, "CSV來源不存在", f"找不到來源CSV檔案：\n{source_csv_path}")
            settings_dict['All Cutting Parameters'] = target_csv_path
            
            # === 儲存STH data ===
            if settings_dict['STH Signal'] != '':
                source_csv_path = os.path.join(base_path, "TemporarySaved", "data", "synchronize_STH_signal.csv")
                target_csv_path = os.path.splitext(file_path)[0] + "_synchronize_STH_signal.csv"
                if os.path.exists(source_csv_path):
                    shutil.copyfile(source_csv_path, target_csv_path)
                    settings_dict['STH Signal'] = target_csv_path
                else:
                    QMessageBox.warning(parent, "CSV來源不存在", f"找不到來源CSV檔案：\n{source_csv_path}")
                

            # === 儲存動畫資料 ===
            target_npy1_path = os.path.splitext(file_path)[0] + "_workpiece.npz"
            target_npy2_path = os.path.splitext(file_path)[0] + "_tool.npz"
            settings_dict['workpiece_for_anime'] = target_npy1_path
            settings_dict['tool_for_anime'] = target_npy2_path
            np.savez_compressed(target_npy1_path, data=np.array(frameClass.cnc.workpiece_for_anime, dtype=object))
            np.savez_compressed(target_npy2_path, data=np.array(frameClass.cnc.tool_for_anime, dtype=object))

            # === 儲存專案檔案 ===
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, indent=4, ensure_ascii=False)

            waiting_dialog.accept()  # 關閉等待視窗

            QMessageBox.information(parent, "儲存成功", f"專案已成功儲存至:\n{file_path}")
            return os.path.basename(file_path)

        except Exception as e:
            if 'waiting_dialog' in locals():
                waiting_dialog.reject()
            QMessageBox.critical(parent, "儲存失敗", f"儲存專案時發生錯誤:\n{str(e)}")
            return None

    
    def load_project(self, loading_dialog, parent=None):
        """
        載入專案功能（帶有"載入中"提示視窗）

        Returns:
            tuple: (檔案名稱, 設定字典)，如果取消或失敗則返回None
        """
        try:
            # 開啟檔案選擇對話框
            file_path, _ = QFileDialog.getOpenFileName(
                parent,
                "開啟專案",
                "","CAM專案 (*.camproj);;JSON檔案 (*.json);;所有檔案 (*)"
            )

            if not file_path:
                return None

            if not os.path.exists(file_path):
                QMessageBox.critical(parent, "檔案不存在", f"找不到檔案: {file_path}")
                return None

            # === 顯示載入中對話框 ===
            
            loading_dialog.setModal(True)
            loading_dialog.setWindowTitle("載入中")
            loading_dialog.setWindowFlags(loading_dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
            layout = QVBoxLayout()
            layout.addWidget(QLabel("正在載入專案，請稍候..."))
            loading_dialog.setLayout(layout)
            loading_dialog.setFixedSize(250, 100)
            loading_dialog.show()
            QApplication.processEvents()

            # === 讀取專案檔案 ===
            with open(file_path, 'r', encoding='utf-8') as f:
                project_data = json.load(f)

            # 驗證格式
            if not self._validate_project_file(project_data):
                loading_dialog.reject()
                QMessageBox.critical(parent, "檔案格式錯誤", "選擇的檔案不是有效的專案檔案")
                return None

            loading_dialog.accept()  # 關閉視窗

            filename = os.path.basename(file_path)
            return filename, project_data.get("settings", {})

        except json.JSONDecodeError:
            if 'loading_dialog' in locals():
                loading_dialog.reject()
            QMessageBox.critical(parent, "檔案格式錯誤", "選擇的檔案不是有效的JSON格式")
            return None

        except Exception as e:
            if 'loading_dialog' in locals():
                loading_dialog.reject()
            QMessageBox.critical(parent, "載入失敗", f"載入專案時發生錯誤:\n{str(e)}")
            return None
    
    def _validate_project_file(self, project_data):
        """
        驗證專案檔案格式
        
        Args:
            project_data (dict): 從檔案載入的資料
            
        Returns:
            bool: 檔案格式是否有效
        """
        if not isinstance(project_data, dict):
            return False
        
        # 檢查必要的欄位
        if "settings" not in project_data:
            return False
        
        # 可以加入更多驗證規則
        return True
    
    def get_recent_projects(self, max_count=5):
        """
        獲取最近使用的專案列表（需要額外實作記錄功能）
        
        Args:
            max_count (int): 最大返回數量
            
        Returns:
            list: 最近專案的路徑列表
        """
        # 這裡可以實作最近專案的記錄功能
        # 例如儲存在設定檔或註冊表中
        pass