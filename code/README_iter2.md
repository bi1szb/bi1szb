# 术中超声可视化工具 Iter2

## 运行

```powershell
python .\code\prostate_us_viewer_iter2.py
```

程序会优先自动加载：

```text
D:\wss_workspace\data\jpg
```

也可以点击“加载文件夹”手动选择同类数据目录。

## 代码结构

```text
prostate_us_viewer_iter2.py       程序入口
us_viewer_iter2/config.py         标定输入和常量
us_viewer_iter2/dataset_io.py     病例目录和图像扫描
us_viewer_iter2/widgets.py        PyQt 图像视图和可拖动图元
us_viewer_iter2/main_window.py    主窗口、绘制、交互和保存恢复
us_viewer_iter2/serialization.py  QPointF 与 json 数组转换
us_viewer_iter2/cutting_plan.py   切割区域数据结构和默认参数
us_viewer_iter2/cutting_items.py  切割区域控制点图元
```

## 刻度线

1. 点击“初始化刻度线”。
2. 输入 `depth`，例如 `3.95`。
3. `scale_10mm_pixel = 790 / depth`。

也可以输入 `depth,系数`，例如：

```text
3.95,800
```

## 切割区域

1. 先初始化刻度线。
2. 点击“确认刻度线”。
3. 点击“初始化切割区域”。

矢状面会生成 `ML / BN / MP / VZ / END` 五个点：

- `ML` 为绿色，其余为橙色。
- 点到刻度线的竖直距离表示深度。
- `ML` 和刻度线起点之间、`END` 和刻度线终点之间也用实线连接。
- 只有 `VZ` 到 `END` 之间显示淡紫色区域，并显示蝴蝶切。
- 拖动矢状面点可调整 X/Y；X 更新对应横断面序号，Y 到刻度线的竖直距离只更新当前点自己的横断面规划半径。

横断面规则：

- 普通切割使用 2 个角度，只显示虚线边界和弧线，不填充区域。
- 蝴蝶切使用 4 个角度，初始为 `-30, -60, 30, 60`；不显示整块淡紫色外区，只显示淡橙色缺口区域。
- 角度 `0` 为 y 轴负方向，顺时针为正。
- 每个规划点保留自己的横断面半径；调整半径只影响当前选中的规划点。
- 圆心和扇形端点显示为圆圈内十字。
- 拖动圆心会平移当前点对应的横断面区域，拖动时控制点会复用，不会反复销毁重建。
- 拖动角度/半径点会改变当前选中点的角度和半径，并联动该点的矢状面深度。

右侧参数面板可选择 `ML / BN / MP / VZ / END`，并编辑：

- 横断面序号
- 圆心 x/y
- 半径
- 角度 1-4

## 保存

刻度线保存到：

```text
planning_line_iter2.json
```

切割区域保存到：

```text
cutting_plan_iter2.json
```

补充：`cutting_plan_iter2.json` 中的切割区域以 `points` 保存 `ML / BN / MP / VZ / END` 五个矢状面关键点。所有横断面图像都会根据五个关键点插值得到当前帧半径、圆心和角度并显示扇形区域；只有五个关键点对应的横断面帧显示可拖动控制点并允许修改，修改半径会同步回左侧对应关键点的深度。
显示范围限制在 `ML` 到 `END` 对应的横断面帧之间；`ML` 之前和 `END` 之后不显示手术规划区域。
约束：角度限制在 `-115` 到 `115` 度；角度顺序固定为 `A1 > A2 > A3 > A4`。半径最大为 30mm，对应像素为 `scale_numerator * 3 / depth`，默认即 `790 * 3 / depth`。切换病例或关闭程序前会保存当前病例的刻度线和切割区域。
`cutting_plan_iter2.json` 从 `version: 3` 开始，`sagittal.transverse_index` 使用 1 开始计数；程序内部仍使用 Python 的 0 开始索引，并兼容读取旧版 0 开始的 json。
从 `version: 4` 开始，横断面半径使用 `transverse.r` 列表保存。普通切割为一个值，例如 `"r": [80]`；蝴蝶切为两个值，例如 `"r": [80, 95]`，前者为 R 侧 `A1-A2` 半径，后者为 L 侧 `A3-A4` 半径。旧版 `radius` 字段读取时会自动转换为 `r`。

## Mask 显示

点击“显示mask”按钮会读取 `data/seg/{patient_id}.nii.gz`，并在当前横断面图像上叠加 mask 边缘线。只显示边缘，不填充区域，避免遮挡手术规划。标签颜色：1 内腺绿色，2 外腺红色，3 膀胱蓝色，4 精囊黄色。
