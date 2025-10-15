import numpy as np
import pandas as pd
from scipy.spatial import KDTree

class CNCDataQuery:
    def __init__(self, csv_path=None, data=None, threshold=0.1):
        if csv_path is None and data is None:
            raise ValueError("必须提供 csv_path 或 data 其中之一")

        if data is not None:
            if isinstance(data, pd.DataFrame):
                self.df = data
            elif isinstance(data, np.ndarray):
                self.df = pd.DataFrame(data)
            elif isinstance(data, list):
                self.df = pd.DataFrame(np.array(data))
            else:
                raise TypeError("data 必须是 list、numpy.ndarray 或 pandas.DataFrame")
        else:
            # 读取CSV文件
            self.df = pd.read_csv(csv_path, skiprows=1, header=None)

        self.threshold = threshold
        self.data = np.array(self.df)

        # 提取XYZ坐标和数据列
        self.points = self.data[:, 0:3]
        self.width = self.data[:, 5]
        self.depth = self.data[:, 6]
        self.area = self.data[:, 7]
        self.gcode_lines = self.data[:, 8]
        self.time = self.data[:, 9]
        
        # 构建KDTree用于快速最近邻搜索
        self.tree = KDTree(self.points)
        
        # 预计算所有线段的方向向量和长度
        self.segments = self._precompute_segments()
        
    def _precompute_segments(self):
        """预计算所有线段信息"""
        segments = []
        for i in range(len(self.points) - 1):
            start_point = self.points[i]
            end_point = self.points[i+1]
            direction = end_point - start_point
            length = np.linalg.norm(direction)
            if length > 0:
                direction = direction / length  # 单位化
            
            segments.append({
                'start_idx': i,
                'end_idx': i+1,
                'start_point': start_point,
                'end_point': end_point,
                'direction': direction,
                'length': length
            })
        return segments
    
    def find_closest_segment(self, query_point):
        """找到查询点最接近的线段"""
        distances, indices = self.tree.query(query_point, k=5)
        
        min_distance = float('inf')
        closest_segment = None
        closest_t = 0
        
        for idx in np.atleast_1d(indices):
            if idx < len(self.segments):
                segment = self.segments[idx]
                distance, t = self._point_to_segment_distance(query_point, segment)
                if distance < min_distance:
                    min_distance = distance
                    closest_segment = segment
                    closest_t = t
            if idx > 0:
                segment = self.segments[idx-1]
                distance, t = self._point_to_segment_distance(query_point, segment)
                if distance < min_distance:
                    min_distance = distance
                    closest_segment = segment
                    closest_t = t
        
        return closest_segment, closest_t, min_distance
    
    def _point_to_segment_distance(self, point, segment):
        """计算点到线段的距离和在线段上的参数化位置"""
        ap = point - segment['start_point']
        t = np.dot(ap, segment['direction'])
        
        if t < 0:
            return np.linalg.norm(point - segment['start_point']), 0
        elif t > segment['length']:
            return np.linalg.norm(point - segment['end_point']), 1
        else:
            projection = segment['start_point'] + t * segment['direction']
            return np.linalg.norm(point - projection), t / segment['length']
    
    def query_point(self, query_point):
        """查询点对应的数据，必要时进行插值"""
        segment, t, distance = self.find_closest_segment(query_point)
        if distance > self.threshold:
            return None
        
        start_width = self.width[segment['start_idx']]
        end_width = self.width[segment['end_idx']]
        
        start_depth = self.depth[segment['start_idx']]
        end_depth = self.depth[segment['end_idx']]
        
        start_area = self.area[segment['start_idx']]
        end_area = self.area[segment['end_idx']]
        
        # start_gcodeLine = self.gcode_lines[segment['start_idx']]
        end_gcodeLine = self.gcode_lines[segment['end_idx']]
        
        start_time = self.time[segment['start_idx']]
        end_time = self.time[segment['end_idx']]
        
        interpolated_width = start_width + t * (end_width - start_width)
        interpolated_depth = start_depth + t * (end_depth - start_depth)
        interpolated_area = start_area + t * (end_area - start_area)
        output_gcodeLine = end_gcodeLine
        interpolated_time = start_time + t * (end_time - start_time)
        
        return {
            'width': interpolated_width,
            'depth': interpolated_depth,
            'area': interpolated_area,
            'GcodeLine': output_gcodeLine,
            'time': interpolated_time,
            'distance_to_path': distance,
            'segment_start_idx': segment['start_idx'],
            'segment_end_idx': segment['end_idx'],
            't_parameter': t
        }
    
    # def batch_query(self, query_points, key):
    #     """批量查询多个点"""
    #     return [self.query_point(point)[key] for point in query_points]
    def batch_query(self, query_points, keys: str | tuple):
        if isinstance(keys, str):
            return [self.query_point(point)[keys] for point in query_points]
        elif isinstance(keys, tuple):
            result_dict = {key: [] for key in keys}
            
            for point in query_points:
                point_data = self.query_point(point)
                for key in keys:
                    if key in point_data:
                        result_dict[key].append(point_data[key])
                    else:
                        result_dict[key].append(None) # 如果字典中沒有該鍵，回傳 None
                        
            return result_dict

