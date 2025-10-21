# import re
# import numpy as np
# import math

# class GcodeParser:
#     def __init__(self):
#         self.cut_paths = []
#         self.subprograms = {}
#         self.GcodeVariable = {}  # 存储变量定义
#         self.spindle_speed = 0
#         self.feed = 0
#         self.controller_type = None  # 'Siemens' 或 'Fanuc'
#         self.current_tool = None  # 当前刀具
#         self.tool_list = []       # 所有使用的刀具列表
        
#         # 支持的函数映射
#         self.supported_functions = {
#             'DC': lambda x: x,  # DC函数直接返回值
#             'SIN': math.sin,
#             'COS': math.cos,
#             'TAN': math.tan,
#             'ABS': abs,
#             'SQRT': math.sqrt,
#             'ROUND': round,
#             'INT': int,
#             'EXP': math.exp,
#             'LN': math.log,
#         }

#     def remove_comments(self, line):
#         """根据控制器类型移除注释"""
#         if self.controller_type == 'Siemens':
#             # Siemens: 分号后面的都是注释
#             return line.split(';')[0].strip()
#         else:  # Fanuc
#             # Fanuc: 括号内的都是注释
#             return re.sub(r'\([^)]*\)', '', line).strip()

#     def parse_math_expression(self, expr_str):
#         """解析数学表达式，支持变量和函数调用"""
#         try:
#             # 移除空格
#             expr_str = expr_str.replace(' ', '')
            
#             # 递归解析表达式
#             return self._evaluate_expression(expr_str)
#         except:
#             # 如果解析失败，返回0
#             return 0.0

#     def _evaluate_expression(self, expr):
#         """递归计算表达式值，支持变量替换"""
#         # 先移除空白
#         expr = expr.strip()

#         # 先替換變數
#         if self.controller_type == 'Siemens':
#             expr = re.sub(r'R(\d+)', 
#                           lambda m: str(self.GcodeVariable.get(m.group(1), 0.0)), 
#                           expr)
#         elif self.controller_type == 'Fanuc':
#             expr = re.sub(r'\#(\d+)', 
#                           lambda m: str(self.GcodeVariable.get(m.group(1), 0.0)), 
#                           expr)

#         # 基础情况：直接数值
#         if re.match(r'^[-+]?\d*\.?\d+$', expr):
#             return float(expr)

#         # 函数调用
#         func_match = re.match(r'^([A-Z]+)\((.*)\)$', expr)
#         if func_match:
#             func_name, param_str = func_match.groups()
#             if func_name in self.supported_functions:
#                 param_value = self._evaluate_expression(param_str)
#                 return self.supported_functions[func_name](param_value)
#             return 0.0

#         # 数学运算（加減乘除）
#         # 注意這裡要用 rsplit，避免把函數裡面的 -,+ 誤切
#         if '+' in expr:
#             left, right = expr.split('+', 1)
#             return self._evaluate_expression(left) + self._evaluate_expression(right)
#         if '-' in expr and not expr.startswith('-'):
#             left, right = expr.split('-', 1)
#             return self._evaluate_expression(left) - self._evaluate_expression(right)
#         if '*' in expr:
#             left, right = expr.split('*', 1)
#             return self._evaluate_expression(left) * self._evaluate_expression(right)
#         if '/' in expr:
#             left, right = expr.split('/', 1)
#             denominator = self._evaluate_expression(right)
#             if denominator != 0:
#                 return self._evaluate_expression(left) / denominator
#             return 0.0

#         # 如果都不行，最後再嘗試轉 float
#         try:
#             return float(expr)
#         except:
#             return 0.0

#     def extract_variables(self, line):
#         """提取变量定义，支持复杂表达式如 R3=R1+100"""
#         clean_line = self.remove_comments(line)
        
#         if self.controller_type == 'Siemens':
#             # Siemens: 查找 R 变量定义，支持复杂表达式
#             pattern = r'\bR(\d+)\s*=\s*([^;\s]+)'
#             matches = re.findall(pattern, clean_line)
#             for var_name, expr_str in matches:
#                 try:
#                     value = self.parse_math_expression(expr_str)
#                     self.GcodeVariable[var_name] = value
#                     print(f"定义变量 R{var_name} = {expr_str} = {value}")
#                 except Exception as e:
#                     print(f"变量定义解析错误 R{var_name} = {expr_str}: {e}")
#         else:  # Fanuc
#             # Fanuc: 查找 # 变量定义
#             pattern = r'\#(\d+)\s*=\s*([^\s]+)'
#             matches = re.findall(pattern, clean_line)
#             for var_name, expr_str in matches:
#                 try:
#                     value = self.parse_math_expression(expr_str)
#                     self.GcodeVariable[var_name] = value
#                     print(f"定义变量 #{var_name} = {expr_str} = {value}")
#                 except Exception as e:
#                     print(f"变量定义解析错误 #{var_name} = {expr_str}: {e}")

#     def parse_value(self, value_str, is_absolute, current_value):
#         """解析数值，支持变量、函数调用和数学表达式"""
#         try:
#             # 解析表达式
#             value = self.parse_math_expression(value_str)
            
#             if is_absolute:  # G90
#                 return value
#             else:  # G91
#                 return current_value + value
#         except Exception as e:
#             print(f"数值解析错误 '{value_str}': {e}")
#             return current_value

#     def parse_coordinate(self, line, axis, current_value, is_absolute):
#         """解析特定坐标轴的值"""
#         # 使用精确匹配，避免误判
#         if self.controller_type == 'Siemens':
#             # Siemens: 支持 X=100.0, X100.0, X=R1, X=DC(0.) 等格式
#             pattern = r'\b' + re.escape(axis) + r'\s*=?\s*([-+]?(?:\d+\.?\d*|\.\d+|R\d+|\#\d+|(?:[A-Z]+\([^)]*\)))(?:[+\-*/](?:\d+\.?\d*|\.\d+|R\d+|\#\d+|(?:[A-Z]+\([^)]*\))))*)'
#         else:  # Fanuc
#             # Fanuc: 支持 X100.0, X#1 等格式
#             pattern = r'\b' + re.escape(axis) + r'\s*([-+]?(?:\d+\.?\d*|\.\d+|\#\d+))'
        
#         match = re.search(pattern, line)
#         if match:
#             value_str = match.group(1)
#             # 检查是否是函数调用或复杂表达式
#             if any(func in value_str for func in self.supported_functions.keys()):
#                 print(f"解析{axis}轴表达式: {value_str}")
            
#             return self.parse_value(value_str, is_absolute, current_value)
#         return current_value

#     def parse_arc_parameters(self, line):
#         """解析圆弧参数：R, I, J, K"""
#         arc_params = {}
        
#         # 解析半径 R
#         r_match = re.search(r'\bR\s*([-+]?(?:\d+\.?\d*|\.\d+))', line)
#         if r_match:
#             r_str = r_match.group(1)
#             try:
#                 arc_params['R'] = self.parse_math_expression(r_str)
#                 print(f"解析圆弧半径 R = {arc_params['R']}")
#             except Exception as e:
#                 print(f"圆弧半径解析错误 R{r_str}: {e}")
        
#         # 解析圆心坐标 I, J, K
#         i_match = re.search(r'\bI\s*([-+]?(?:\d+\.?\d*|\.\d+))', line)
#         if i_match:
#             i_str = i_match.group(1)
#             try:
#                 arc_params['I'] = self.parse_math_expression(i_str)
#                 print(f"解析圆心坐标 I = {arc_params['I']}")
#             except Exception as e:
#                 print(f"圆心坐标解析错误 I{i_str}: {e}")
                
#         j_match = re.search(r'\bJ\s*([-+]?(?:\d+\.?\d*|\.\d+))', line)
#         if j_match:
#             j_str = j_match.group(1)
#             try:
#                 arc_params['J'] = self.parse_math_expression(j_str)
#                 print(f"解析圆心坐标 J = {arc_params['J']}")
#             except Exception as e:
#                 print(f"圆心坐标解析错误 J{j_str}: {e}")
                
#         k_match = re.search(r'\bK\s*([-+]?(?:\d+\.?\d*|\.\d+))', line)
#         if k_match:
#             k_str = k_match.group(1)
#             try:
#                 arc_params['K'] = self.parse_math_expression(k_str)
#                 print(f"解析圆心坐标 K = {arc_params['K']}")
#             except Exception as e:
#                 print(f"圆心坐标解析错误 K{k_str}: {e}")
        
#         return arc_params

#     def parse_tool_change(self, line):
#         """解析换刀指令"""
#         tool_match = re.search(r'\bT(\d+)', line)
#         if tool_match:
#             tool_num = int(tool_match.group(1))
#             tool_id = f"T{tool_num:02d}"  # 格式化为 T01, T05 等
            
#             self.current_tool = tool_id
#             if tool_id not in self.tool_list:
#                 self.tool_list.append(tool_id)
#                 print(f"添加新刀具: {tool_id}")
            
#             print(f"换刀指令: 当前刀具 {tool_id}")
#             return True
#         return False

#     def parse_feed_spindle(self, line):
#         """解析进给率和主轴转速，支持 F=数值 格式"""
#         # 进给率 F
#         if self.controller_type == 'Siemens':
#             # Siemens: 支持 F=1000 或 F1000
#             feed_match = re.search(r'\bF\s*=?\s*([-+]?(?:\d+\.?\d*|\.\d+|R\d+)(?:[+\-*/](?:\d+\.?\d*|\.\d+|R\d+))*)', line)
#         else:  # Fanuc
#             feed_match = re.search(r'\bF\s*([-+]?(?:\d+\.?\d*|\.\d+|\#\d+))', line)
        
#         if feed_match:
#             feed_str = feed_match.group(1)
#             try:
#                 self.feed = self.parse_math_expression(feed_str)
#                 print(f"设置进给率 F = {feed_str} = {self.feed}")
#             except Exception as e:
#                 print(f"进给率解析错误 F{feed_str}: {e}")
        
#         # 主轴转速 S
#         if self.controller_type == 'Siemens':
#             spindle_match = re.search(r'\bS\s*=?\s*([-+]?(?:\d+\.?\d*|\.\d+|R\d+)(?:[+\-*/](?:\d+\.?\d*|\.\d+|R\d+))*)', line)
#         else:  # Fanuc
#             spindle_match = re.search(r'\bS\s*([-+]?(?:\d+\.?\d*|\.\d+|\#\d+))', line)
        
#         if spindle_match:
#             spindle_str = spindle_match.group(1)
#             try:
#                 self.spindle_speed = self.parse_math_expression(spindle_str)
#                 print(f"设置主轴转速 S = {spindle_str} = {self.spindle_speed}")
#             except Exception as e:
#                 print(f"主轴转速解析错误 S{spindle_str}: {e}")

#     def parse_gcode(self, gcode, controller_type='Fanuc'):
#         """解析Gcode主函数"""
#         self.controller_type = controller_type
#         self.cut_paths = []
#         self.subprograms = {}
#         self.GcodeVariable = {}
#         self.current_tool = None
#         self.tool_list = []
        
#         x, y, z, c, a = 0, 0, 0, 0, 0
#         is_absolute = True  # 默认绝对坐标
#         current_motion_mode = 'G0'  # 默认移动模式
#         self.feed = 0
#         self.spindle_speed = 0

#         # 主解析循环
#         line_number = 0
#         for original_line in gcode:
#             line_number += 1
#             # 移除注释
#             clean_line = self.remove_comments(original_line)
#             if not clean_line:
#                 continue
            
#             print(f"\n解析第{line_number}行: {original_line.strip()}")
#             print(f"清理后: {clean_line}")
            
#             # 移除行号（如果有）
#             clean_line_no_n = re.sub(r'^N\d+\s*', '', clean_line).strip()
#             if not clean_line_no_n:
#                 continue
            
#             # 提取变量定义（必须在解析坐标之前）
#             self.extract_variables(clean_line)
            
#             # 解析换刀指令
#             self.parse_tool_change(clean_line)
            
#             # 解析G90/G91（绝对/相对坐标）
#             if 'G90' in clean_line:
#                 is_absolute = True
#                 print("切换到绝对坐标模式 (G90)")
#             elif 'G91' in clean_line:
#                 is_absolute = False
#                 print("切换到相对坐标模式 (G91)")
            
#             # 解析运动模式 - 扩展支持 G2, G3, G02, G03
#             motion_match = re.search(r'\bG0*([0-3])\b', clean_line, re.IGNORECASE)
#             if motion_match:
#                 current_motion_mode = f'G{motion_match.group(1)}'
#                 print(f"運動模式: {current_motion_mode}")
            
#             # 解析进给率和主轴转速
#             self.parse_feed_spindle(clean_line)
            
#             # 解析子程序调用
#             if 'M98' in clean_line and self.controller_type == 'Fanuc':
#                 sub_call_match = re.search(r'M98\s+[PQ](\d+)', clean_line)
#                 if sub_call_match:
#                     sub_num = sub_call_match.group(1)
#                     print(f"调用子程序: {sub_num}")
#                     # 这里可以添加子程序处理逻辑
            
#             # 解析坐标值
#             new_x = self.parse_coordinate(clean_line, 'X', x, is_absolute)
#             new_y = self.parse_coordinate(clean_line, 'Y', y, is_absolute)
#             new_z = self.parse_coordinate(clean_line, 'Z', z, is_absolute)
#             new_c = self.parse_coordinate(clean_line, 'C', c, is_absolute)
#             new_a = self.parse_coordinate(clean_line, 'A', a, is_absolute)
            
#             # 检查是否有坐标变化
#             coordinates_changed = (new_x != x or new_y != y or new_z != z or 
#                                  new_c != c or new_a != a)
            
#             # 解析圆弧参数（如果是圆弧插补）
#             arc_params = {}
#             if current_motion_mode in ['G2', 'G3', 'G02', 'G03']:
#                 arc_params = self.parse_arc_parameters(clean_line)
            
#             if coordinates_changed or arc_params:
#                 x, y, z, c, a = new_x, new_y, new_z, new_c, new_a
                
#                 # 创建路径信息，包含圆弧参数
#                 path_info = {
#                     'motion_mode': current_motion_mode,
#                     'line_number': line_number,
#                     'target_pose': np.array([x, y, z, c, a]),
#                     'feed': self.feed,
#                     'spindle_speed': self.spindle_speed,
#                     'arc_params': arc_params,  # 圆弧参数
#                     'current_tool': self.current_tool  # 当前刀具
#                 }
                
#                 self.cut_paths.append(path_info)
#                 print(f"坐标更新: X={x}, Y={y}, Z={z}, C={c}, A={a}")
#                 if arc_params:
#                     print(f"圆弧参数: {arc_params}")

#         # 解析完成后输出刀具列表
#         print(f"\n解析完成！使用的刀具列表: {self.tool_list}")

import re
import numpy as np
import math

class GcodeParser:
    def __init__(self):
        self.cut_paths = []
        self.subprograms = {}
        self.GcodeVariable = {}
        self.spindle_speed = 0
        self.feed = 0
        self.controller_type = None  # 'Siemens' or 'Fanuc'
        self.current_tool = ''    # tool_id
        self.tool_list = []

        self.supported_functions = {
            'DC': lambda x: x,
            'SIN': math.sin, 'COS': math.cos, 'TAN': math.tan,
            'ABS': abs, 'SQRT': math.sqrt, 'ROUND': round,
            'INT': int, 'EXP': math.exp, 'LN': math.log,
        }

    def remove_comments(self, line):
        if self.controller_type == 'Siemens':
            return line.split(';')[0].strip()
        else:
            return re.sub(r'\([^)]*\)', '', line).strip()

    def extract_comment_from_line(self, line):
        """Return comment content (without parentheses/semicolon), or None."""
        if not line:
            return None
        if self.controller_type == 'Siemens':
            if ';' in line:
                return line.split(';', 1)[1].strip()
            return None
        else:
            m = re.search(r'\(([^)]*)\)', line)
            if m:
                return m.group(1).strip()
            return None

    # --- math/variable parsing (unchanged) ---
    def parse_math_expression(self, expr_str):
        try:
            expr_str = expr_str.replace(' ', '')
            return self._evaluate_expression(expr_str)
        except:
            return 0.0

    def _evaluate_expression(self, expr):
        expr = expr.strip()
        if self.controller_type == 'Siemens':
            expr = re.sub(r'R(\d+)', lambda m: str(self.GcodeVariable.get(m.group(1), 0.0)), expr)
        elif self.controller_type == 'Fanuc':
            expr = re.sub(r'\#(\d+)', lambda m: str(self.GcodeVariable.get(m.group(1), 0.0)), expr)

        if re.match(r'^[-+]?\d*\.?\d+$', expr):
            return float(expr)

        func_match = re.match(r'^([A-Z]+)\((.*)\)$', expr)
        if func_match:
            func_name, param_str = func_match.groups()
            if func_name in self.supported_functions:
                param_value = self._evaluate_expression(param_str)
                return self.supported_functions[func_name](param_value)
            return 0.0

        # simple ops
        # order is simplified; works for typical expressions used here
        if '+' in expr:
            left, right = expr.split('+', 1)
            return self._evaluate_expression(left) + self._evaluate_expression(right)
        if '-' in expr and not expr.startswith('-'):
            left, right = expr.split('-', 1)
            return self._evaluate_expression(left) - self._evaluate_expression(right)
        if '*' in expr:
            left, right = expr.split('*', 1)
            return self._evaluate_expression(left) * self._evaluate_expression(right)
        if '/' in expr:
            left, right = expr.split('/', 1)
            denom = self._evaluate_expression(right)
            if denom != 0:
                return self._evaluate_expression(left) / denom
            return 0.0

        try:
            return float(expr)
        except:
            return 0.0

    def extract_variables(self, line):
        clean_line = self.remove_comments(line)
        if self.controller_type == 'Siemens':
            pattern = r'\bR(\d+)\s*=\s*([^;\s]+)'
            matches = re.findall(pattern, clean_line)
            for var_name, expr_str in matches:
                try:
                    value = self.parse_math_expression(expr_str)
                    self.GcodeVariable[var_name] = value
                    print(f"定义变量 R{var_name} = {expr_str} = {value}")
                except Exception as e:
                    print(f"变量定义解析错误 R{var_name} = {expr_str}: {e}")
        else:
            pattern = r'\#(\d+)\s*=\s*([^\s]+)'
            matches = re.findall(pattern, clean_line)
            for var_name, expr_str in matches:
                try:
                    value = self.parse_math_expression(expr_str)
                    self.GcodeVariable[var_name] = value
                    # print(f"定义变量 #{var_name} = {expr_str} = {value}")
                except Exception as e:
                    print(f"变量定义解析错误 #{var_name} = {expr_str}: {e}")

    def parse_value(self, value_str, is_absolute, current_value):
        try:
            value = self.parse_math_expression(value_str)
            return value if is_absolute else current_value + value
        except Exception as e:
            print(f"数值解析错误 '{value_str}': {e}")
            return current_value

    def parse_coordinate(self, line, axis, current_value, is_absolute):
        if self.controller_type == 'Siemens':
            pattern = r'\b' + re.escape(axis) + r'\s*=?\s*([-+]?(?:\d+\.?\d*|\.\d+|R\d+|\#\d+|(?:[A-Z]+\([^)]*\)))(?:[+\-*/](?:\d+\.?\d*|\.\d+|R\d+|\#\d+|(?:[A-Z]+\([^)]*\))))*)'
        else:
            pattern = r'\b' + re.escape(axis) + r'\s*([-+]?(?:\d+\.?\d*|\.\d+|\#\d+))'
        match = re.search(pattern, line)
        if match:
            value_str = match.group(1)
            if any(func in value_str for func in self.supported_functions.keys()):
                print(f"解析{axis}轴表达式: {value_str}")
            return self.parse_value(value_str, is_absolute, current_value)
        return current_value

    def parse_arc_parameters(self, line):
        arc_params = {}
        r_match = re.search(r'\bR\s*([-+]?(?:\d+\.?\d*|\.\d+))', line)
        if r_match:
            r_str = r_match.group(1)
            try:
                arc_params['R'] = self.parse_math_expression(r_str)
                # print(f"解析圆弧半径 R = {arc_params['R']}")
            except Exception as e:
                print(f"圆弧半径解析错误 R{r_str}: {e}")
        for axis in ['I', 'J', 'K']:
            m = re.search(r'\b' + axis + r'\s*([-+]?(?:\d+\.?\d*|\.\d+))', line)
            if m:
                s = m.group(1)
                try:
                    arc_params[axis] = self.parse_math_expression(s)
                    # print(f"解析圆心坐标 {axis} = {arc_params[axis]}")
                except Exception as e:
                    print(f"圆心坐标解析错误 {axis}{s}: {e}")
        return arc_params

    def parse_tool_change(self, line, tool_comment=None):
        """如果 line 含 T 指令就更新 current_tool (tool_id, tool_comment_or_None)"""
        tool_match = re.search(r'\bT(\d+)\b', line)
        if tool_match:
            tool_num = int(tool_match.group(1))
            tool_id = f"T{tool_num}"
            self.current_tool = tool_id
            if tool_id not in self.tool_list:
                self.tool_list.append((tool_id, tool_comment))
                # print(f"添加新刀具: {tool_id}")
            if tool_comment:
                print(f"换刀指令: 当前刀具 {tool_id}，註解: {tool_comment}")
            else:
                print(f"换刀指令: 当前刀具 {tool_id}，無註解")
            return True
        return False

    def parse_feed_spindle(self, line):
        if self.controller_type == 'Siemens':
            feed_match = re.search(r'\bF\s*=?\s*([-+]?(?:\d+\.?\d*|\.\d+|R\d+)(?:[+\-*/](?:\d+\.?\d*|\.\d+|R\d+))*)', line)
        else:
            feed_match = re.search(r'\bF\s*([-+]?(?:\d+\.?\d*|\.\d+|\#\d+))', line)
        if feed_match:
            feed_str = feed_match.group(1)
            try:
                self.feed = self.parse_math_expression(feed_str)
                # print(f"设置进给率 F = {feed_str} = {self.feed}")
            except Exception as e:
                print(f"进给率解析错误 F{feed_str}: {e}")

        if self.controller_type == 'Siemens':
            spindle_match = re.search(r'\bS\s*=?\s*([-+]?(?:\d+\.?\d*|\.\d+|R\d+)(?:[+\-*/](?:\d+\.?\d*|\.\d+|R\d+))*)', line)
        else:
            spindle_match = re.search(r'\bS\s*([-+]?(?:\d+\.?\d*|\.\d+|\#\d+))', line)
        if spindle_match:
            spindle_str = spindle_match.group(1)
            try:
                self.spindle_speed = self.parse_math_expression(spindle_str)
                # print(f"设置主轴转速 S = {spindle_str} = {self.spindle_speed}")
            except Exception as e:
                print(f"主轴转速解析错误 S{spindle_str}: {e}")

    def parse_gcode(self, gcode, controller_type, progress_signal=None):
        self.controller_type = controller_type
        self.cut_paths = []
        self.subprograms = {}
        self.GcodeVariable = {}
        self.current_tool = None
        self.tool_list = []

        x = y = z = c = a = 0.0
        is_absolute = True
        current_motion_mode = 'G0'
        self.feed = 0
        self.spindle_speed = 0
        total_lines = len(gcode)
        progress_value = 0.0
        progress_increase = 1000.0/total_lines
        for i, original_line in enumerate(gcode):
            
            progress_value = max(0.0, progress_value + progress_increase)
            if i%1000 == 0:
                if progress_signal:
                    progress_signal.emit(progress_value)
            clean_line = self.remove_comments(original_line)
            if not clean_line:
                # 若該行僅為註解，跳過（換刀註解會在換刀那行或其相鄰行被檢查）
                continue

            line_number = i + 1
            # print(f"\n解析第{line_number}行: {original_line.strip()}")
            # print(f"清理后: {clean_line}")

            # 移除行號
            clean_line_no_n = re.sub(r'^N\d+\s*', '', clean_line).strip()
            if not clean_line_no_n:
                continue

            # 變數定義
            self.extract_variables(clean_line)

            # --- 只有在該行含 T 指令時才搜尋附近註解 ---
            if re.search(r'\bT\d+\b', clean_line_no_n):
                # 取得當前/下一/前一行的註解（不會使用名稱 c 去暫存）
                comment_here = self.extract_comment_from_line(original_line)
                comment_next = self.extract_comment_from_line(gcode[i+1]) if (i + 1) < total_lines else None
                comment_prev = self.extract_comment_from_line(gcode[i-1]) if i - 1 >= 0 else None

                tool_comment_candidate = None
                for comm in (comment_here, comment_next, comment_prev):
                    if comm and re.search(r'\btoolname\s*=', comm, re.IGNORECASE):
                        tool_comment_candidate = comm.strip()
                        break
                # 傳入註解（若有）
                self.parse_tool_change(clean_line_no_n, tool_comment_candidate)
            else:
                # 若沒有 T 指令，仍呼叫 parse_tool_change 讓 parse_tool_change 只在必要情況動作
                self.parse_tool_change(clean_line_no_n, None)

            # G90/G91
            if 'G90' in clean_line_no_n:
                is_absolute = True
                # print("切换到绝对坐标模式 (G90)")
            elif 'G91' in clean_line_no_n:
                is_absolute = False
                # print("切换到相对坐标模式 (G91)")

            motion_match = re.search(r'\bG0*([0-3])\b', clean_line_no_n, re.IGNORECASE)
            if motion_match:
                current_motion_mode = f'G{motion_match.group(1)}'
                # print(f"運動模式: {current_motion_mode}")

            self.parse_feed_spindle(clean_line_no_n)

            if 'M98' in clean_line_no_n and self.controller_type == 'Fanuc':
                sub_call_match = re.search(r'M98\s+[PQ](\d+)', clean_line_no_n)
                if sub_call_match:
                    sub_num = sub_call_match.group(1)
                    # print(f"调用子程序: {sub_num}")

            new_x = self.parse_coordinate(clean_line_no_n, 'X', x, is_absolute)
            new_y = self.parse_coordinate(clean_line_no_n, 'Y', y, is_absolute)
            new_z = self.parse_coordinate(clean_line_no_n, 'Z', z, is_absolute)
            new_c = self.parse_coordinate(clean_line_no_n, 'C', c, is_absolute)
            new_a = self.parse_coordinate(clean_line_no_n, 'A', a, is_absolute)

            coordinates_changed = (new_x != x or new_y != y or new_z != z or new_c != c or new_a != a)

            arc_params = {}
            if current_motion_mode in ['G2', 'G3', 'G02', 'G03']:
                arc_params = self.parse_arc_parameters(clean_line_no_n)

            if coordinates_changed or arc_params:
                x, y, z, c, a = new_x, new_y, new_z, new_c, new_a
                path_info = {
                    'motion_mode': current_motion_mode,
                    'line_number': line_number,
                    'target_pose': np.array([x, y, z, c, a]),
                    'feed': self.feed,
                    'spindle_speed': self.spindle_speed,
                    'arc_params': arc_params,
                    'current_tool': self.current_tool
                }
                self.cut_paths.append(path_info)
                # print(f"坐标更新: X={x}, Y={y}, Z={z}, C={c}, A={a}")
                # if arc_params:
                    # print(f"圆弧参数: {arc_params}")

        # print(f"\n解析完成！使用的刀具列表: {self.tool_list}")
        if progress_signal:
            progress_signal.emit(1000.0)


# parser = GcodeParser()
# gcode = [
#     "N100 G90 G00 X0 Y0 Z100",
#     "T01 M06 (toolname=D10R1-50_100_MST)", # 当前行有 T 指令 和注释
#     "G00 X50 Y50 Z5 M3 S1000 F200",
#     "G01 Z-5",
#     "M05",
#     "T02", # T 指令
#     "(toolname=C10-00_50_MST)", # 紧邻的下一行有注释
#     "M06",
#     "G00 X0 Y0 Z100",
#     "T03 M06", # T 指令，没有紧邻注释
#     "G00 X-50 Y-50 Z5",
#     "T5", # T 指令

#     "M06",
#     "G00 Z100"
# ]
# # gcode = ['G00 Z92.35',
# # 'X105.18 Y90.041',
# # 'Z83.',
# # 'G03 X107.861 Y89.379 Z82.854 R5.76',
# # 'T05 M6',
# # '(toolname=D8R1-35_80_MST)',
# # 'X107.861 Y89.379 Z82.854 I3. J4. K5.'
# # ]
# parser.parse_gcode(gcode)
# print(parser.cut_paths)