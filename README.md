# Modbus TCP 数据采集程序

通过 Modbus TCP 协议持续采集西门子 PLC 的数据，支持多种数据类型，自动保存 CSV 文件。

## 功能特点

- 自动读取 TIA Portal 导出的 Excel 变量表，适配不同 PLC 项目
- 支持 `Int`、`Word`、`DInt`、`DWord`、`Real`、`Bool` 等数据类型
- 持续轮询采集，终端表格实时刷新
- 自动分文件保存 CSV，旧文件自动清理
- 断线自动重连
- 修改 Excel 即可适配新项目，无需改代码

## 项目结构

```
├── main.py                # 配置中心 + 启动入口（所有参数在此修改）
├── data_acquisition.py    # 数据采集逻辑封装（连接、读取、重连）
├── modbus_client.py       # Modbus TCP 通讯封装（支持 FC01~FC10）
├── data_converter.py      # 数据类型转换（寄存器值 ↔ 实际值）
├── excel_reader.py        # Excel 变量表读取（解析 TIA Portal 导出格式）
├── csv_manager.py         # CSV 文件管理（创建、轮转、清理）
├── display.py             # 终端表格显示
├── Modbus_Map.xlsx        # 变量表（TIA Portal 导出格式）
└── requirements.txt       # Python 依赖库
```

## 环境要求

- Python 3.10+
- pymodbus >= 3.0.0
- openpyxl >= 3.0.0

## 安装

```bash
pip install -r requirements.txt
```

## 快速开始

### 1. 准备变量表

从 TIA Portal 导出 DB 块变量表为 Excel 文件，格式如下：

| 变量名 | 数据类型 | 字节偏移 |
|--------|---------|---------|
| 温度传感器 | Real | 0 |
| 压力传感器 | Real | 4 |
| 运行状态 | Bool | 8.1 |

> 支持的数据类型：`Int`、`Word`、`DInt`、`DWord`、`Real`、`Bool`
> 数组父行（如 `Array[0..9] of Int`）会自动跳过
> Bool 类型支持位寻址（如 8.1 表示字节8的第1位）

将文件命名为 `Modbus_Map.xlsx` 放在程序同目录下。

### 2. 修改配置

打开 `main.py`，修改顶部配置区：

```python
PLC_IP = "192.168.0.1"           # PLC 的 IP 地址
PLC_PORT = 502                   # Modbus TCP 端口
UNIT_ID = 1                      # 从站 ID
TIMEOUT = 3                      # 超时时间（秒）
SAMPLE_INTERVAL_MS = 1000        # 采集间隔（毫秒）
MAP_FILE = "Modbus_Map.xlsx"     # 变量表文件名
ROWS_PER_FILE = 30               # 每个 CSV 保存的数据行数
MAX_CSV_FILES = 6                # 最多保留的 CSV 文件数量
```

### 3. 运行

```bash
python main.py
```

输出示例：

```
已连接到 192.168.0.1:502
变量表: Modbus_Map.xlsx（10 个变量）
读取范围: 地址 0~5
采集间隔: 1000ms | 每 30 条换文件 | 保留 6 个
按 Ctrl+C 停止

[2026-05-20 14:30:15.123]
变量名                          偏移量        类型        值               描述
--------------------------------------------------------------------------------
温度传感器                       字节0         float32     25.3
压力传感器                       字节4         float32     101.3
运行状态                         字节8.位1     bit_1       true
```

按 `Ctrl+C` 停止采集。

## 地址换算规则

TIA Portal DB 块中的字节偏移与 Modbus 地址的关系：

```
Modbus 地址 = DB 字节偏移 ÷ 2
```

示例：

| DB 字节偏移 | 数据类型 | Modbus 地址 | 说明 |
|------------|---------|------------|------|
| 0 | Int（2字节） | 0 | 占 1 个寄存器 |
| 4 | Real（4字节） | 2 | 占 2 个寄存器 |
| 8.1 | Bool（1位） | 4.01 | 位寻址 |

> 程序自动完成换算，Excel 中直接填字节偏移即可。

## CSV 保存策略

- 每采集 `ROWS_PER_FILE` 条数据自动创建新文件
- 文件夹内仅保留最新的 `MAX_CSV_FILES` 个文件
- 旧文件自动删除
- 文件名格式：`data_log_20260520_143015.csv`

## PLC 端配置要求

西门子 S7-1200/1500 需在 TIA Portal 中配置 `MB_SERVER` 功能块：

- `IP_PORT`：502
- `MB_HOLD_REG`：指向 DB 块，覆盖所有需要读取的变量区域
- `S7_Optimized_Access`：DB 块必须**关闭**优化访问
- DB 块大小需覆盖到最大字节偏移

## 许可证

MIT License
