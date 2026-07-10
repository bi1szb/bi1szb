# Prostate Ultrasound Viewer Iter3 说明文档

`iter3` 是术中前列腺超声图像可视化工具的第三版。它在 `iter2` 的基础上重点增强了切割规划 JSON 的导入能力：规划点不再限制为固定的 `ML/BN/MP/VZ/END` 五个点，而是 JSON 中有多少点就显示多少点。

## 1. 入口文件

运行入口：

```powershell
python .\code\prostate_us_viewer_iter3.py
```

入口逻辑在：

```text
code/prostate_us_viewer_iter3.py
```

启动流程：

1. 创建 `QApplication`
2. 创建 `MainWindow`
3. 自动尝试加载默认数据目录
4. 显示主窗口

默认查找的数据目录顺序：

```text
D:\wss_workspace\data\jpg
当前目录\data\jpg
当前目录\dataset
D:\wss_workspace\dataset
```

## 2. 代码结构

iter3 独立代码目录：

```text
code/us_viewer_iter3/
```

主要文件：

```text
main_window.py      主窗口、交互逻辑、图像显示、切割规划、mask 显示
cutting_plan.py     切割规划数据结构和常量
cutting_items.py    可拖动规划点图形项
widgets.py          图像视图、规划线控制点、当前帧虚线
dataset_io.py       病人目录、矢状面和横断面图像查找
serialization.py    QPointF 与 list 的转换
config.py           depth/scale 解析和基础常量
```

## 3. 数据目录要求

输入是病人总目录，例如：

```text
data/jpg/
  S00002/
    us_sagittal/
      *.jpg
    us_transverse/
      *.jpg
  S00003/
    us_sagittal/
    us_transverse/
```

矢状面图像：

- 在 `us_sagittal` 目录下查找
- 优先选择文件名 stem 中包含 `1` 的 jpg
- 如果没有，则使用第一个 jpg

横断面图像：

- 在 `us_transverse` 目录下查找全部 jpg
- 按文件名中的 `-001`、`-002` 这类数字后缀排序

## 4. 主界面功能

主界面分为：

```text
左侧：矢状面图像和刻度线/切割点
右侧：横断面图像、切割扇形、mask 边缘和参数面板
```

主要按钮：

```text
加载文件夹
上一例
下一例
初始化刻度线
确认刻度线
初始化切割区域
导入规划JSON
显示mask
```

## 5. 刻度线逻辑

点击“初始化刻度线”后需要输入 `depth`。

`scale_10mm_pixel` 计算方式：

```text
scale_10mm_pixel = 790 / depth
```

也支持输入第二个参数覆盖默认 790：

```text
depth, scale_numerator
```

例如：

```text
1.6
```

或者：

```text
1.6, 790
```

刻度线初始化：

- 零点在矢状面水平 `1/6`、垂直中心
- 起点在矢状面水平 `1/3`、垂直中心
- 刻度线方向由零点和起点确定
- 终点从零点沿该方向延伸
- 横断面每一帧对应 1mm 小刻度

刻度线确认：

- 必须点击“确认刻度线”后，才能初始化或导入切割规划

## 6. 切割规划数据模型

核心数据结构是 `CuttingPlanPoint`：

```python
@dataclass
class CuttingPlanPoint:
    name: str
    sagittal_point: QPointF
    transverse_index: int
    center: QPointF
    radius: float
    angles: list[float]
    radii: list[float]
```

字段含义：

```text
name              点名，例如 ML、BN、MP、VZ、END、MP_VZ_1
sagittal_point    矢状面显示点
transverse_index  横断面索引，内部从 0 开始
center            横断面扇形圆心
radius            主半径
angles            角度列表
radii             半径列表
```

普通切割：

```json
"r": [80.0],
"angles": [60.0, -60.0]
```

蝴蝶切：

```json
"r": [164.2, 162.98],
"angles": [102.86, 30.0, -45.04, -84.1]
```

角度限制：

```text
-115° 到 115°
A1 > A2 > A3 > A4
```

## 7. JSON 导入格式

iter3 推荐使用横断面索引作为字典 key。

示例：

```json
{
  "points": {
    "30": {
      "name": "ML",
      "center": [560.0, 420.0],
      "r": [80.0],
      "angles": [60.0, -60.0]
    },
    "48": {
      "name": "MP_VZ_1",
      "center": [561.0, 420.0],
      "r": [132.0],
      "angles": [72.0, -62.0]
    },
    "53": {
      "name": "VZ",
      "center": [560.0, 420.0],
      "r": [164.2, 162.98],
      "angles": [102.86, 30.0, -45.04, -84.1]
    }
  }
}
```

规则：

- `points` 的 key 是横断面图片序号，从 1 开始
- `name` 是显示名称
- `center` 是横断面圆心像素坐标
- `r` 是半径列表
- `angles` 是角度列表

导入后：

- key 会转换成内部 `transverse_index`
- `name` 会作为点名显示在矢状面和右侧参数面板
- 矢状面点根据横断面索引和半径自动生成

## 8. 任意数量点的支持

iter3 不再固定只支持五个点。

读取 JSON 后：

1. 按 `transverse_index` 从小到大排序
2. 相邻点之间进行插值
3. 横断面当前帧落在哪两个点之间，就根据这两个点插值得到当前扇形

例如：

```text
ML -> ML_BN_1 -> BN -> BN_MP_1 -> MP -> MP_VZ_1 -> VZ -> VZ_END_1 -> END
```

每一段都会独立插值。

## 9. 插值逻辑

普通切割到普通切割：

```text
r 单值插值
angles 两个角度逐项插值
```

蝴蝶切到蝴蝶切：

```text
r 两个半径逐项插值
angles 四个角度逐项插值
```

普通切割到蝴蝶切：

```text
普通切割使用外侧边界参与插值
普通 [A1, A2] 对应蝴蝶 [A1, A4]
半径使用主半径连续插值
```

这样可以避免从普通段进入蝴蝶切段时角度突然跳回默认值。

## 10. 横断面显示

当前横断面规划区域由 `current_cut_region()` 生成。

流程：

1. 根据当前橙色虚线位置计算横断面帧序号
2. 找到该帧位于哪两个关键点之间
3. 插值得到当前帧的圆心、半径、角度
4. 绘制扇形区域和控制点

普通切割：

- 显示两个角度点
- 显示一个扇形边界
- 不显示填充区域

蝴蝶切：

- 显示四个角度点
- `A1-A2` 对应右侧半径
- `A3-A4` 对应左侧半径
- `A2-A3` 缺口区域按深浅橙色显示

## 11. 矢状面显示

矢状面显示：

- 刻度线
- 当前帧橙色虚线
- 切割点
- 点到刻度线的虚线
- 相邻点连线
- 蝴蝶切区域的深/浅紫色区域

如果某个点是双半径：

```text
R 对应 A1-A2
L 对应 A3-A4
```

显示为：

```text
点名R
点名L
```

如果 R/L 重合，则只显示一个点名。

## 12. 拖动交互

矢状面：

- 拖动点会修改同源 `cut_plan`
- 拖动过程中实时刷新矢状面规划区域
- 拖动过程中实时刷新横断面规划区域
- 右侧参数面板和 JSON 保存延后到释放鼠标后

横断面：

- 拖动圆心会移动当前关键点圆心
- 拖动角度点会修改角度和半径
- 只有当前帧正好是关键点时，才允许把修改写回关键点
- 非关键点帧使用插值结果显示

## 13. mask 显示

点击“显示mask”后，程序会查找：

```text
data/seg/{patient_id}.nii.gz
```

标签含义：

```text
1 内腺  绿色
2 外腺  红色
3 膀胱  蓝色
4 精囊  黄色
```

显示方式：

- 只显示 mask 边缘实线
- 不显示填充区域
- 避免覆盖切割规划区域

## 14. 保存文件

iter3 使用独立保存文件：

```text
planning_line_iter3.json
cutting_plan_iter3.json
```

自动读取候选：

```text
cutting_plan_iter3.json
cutting_plan_import.json
```

不会自动读取 `cutting_plan_iter2.json`，避免 v2/v3 状态互相影响。

## 15. 常用测试 JSON

当前示例测试文件：

```text
data/jpg/S00002/cutting_plan_import_more_points_1.json
data/jpg/S00002/cutting_plan_import_more_points_2.json
data/jpg/S00002/cutting_plan_import_more_points_mixed.json
```

这些文件用于测试：

- 多于五个关键点
- 相邻点插值
- 普通切割到蝴蝶切过渡
- 蝴蝶切到蝴蝶切过渡

## 16. 基础验证

修改代码后建议先运行：

```powershell
python -m py_compile .\code\prostate_us_viewer_iter3.py .\code\us_viewer_iter3\main_window.py
```

如果没有输出，说明语法和导入层面没有错误。

## 17. 使用建议

推荐流程：

1. 运行 iter3
2. 加载数据目录
3. 初始化刻度线
4. 确认刻度线
5. 导入规划 JSON
6. 检查矢状面和横断面的联动
7. 只在关键点帧修改横断面参数
8. 切换病例或关闭程序前保存

