# Earth dataset downloader

Aurora 论文数据集下载工具，支持**最近网格点**和**坐标附近区域**。可独立运行于 Linux 服务器，不依赖原来的 Windows 工作目录，也不需要 GPU。

默认位置 **120.33°E、36.30°N**，所有参数均可修改。[完整数据集清单和各来源操作说明](README_zh.md)。

## Linux 服务器快速开始

需要 Git、Python **3.11+**、pip/venv，以及访问对应数据源的网络。

```bash
git clone https://github.com/Aersd1/earthdataset_download.git
cd earthdataset_download
bash setup.sh

# 无需账号：先下载一天 ERA5 最近点的小样本
bash examples/nearest_point.sh
```

输出到 `downloads/era5_nearest/`，包括 NetCDF、CSV 和请求记录。示例默认日期为 **2020-01-01**，不是当前日期。
该坐标的 ERA5 0.25° 最近点为 **120.25°E、36.25°N**，距目标约 **9.07 km**。`--point`（别名 `--nearest`）直接取网格值，不插值。

若服务器默认 Python 太旧，指定已有的新版本解释器：

```bash
PYTHON_BIN=python3.12 bash setup.sh
```

如果提示缺少 `venv`，需要通过服务器的软件包管理器安装对应 Python 的 venv 组件，或使用已有 Conda Python 3.11+ 环境。安装脚本不会修改系统 Python，也不要求管理员权限。

## 改日期、位置、存储目录

```bash
# 最近点，指定日期；长时间下载请先阅读下方“带宽和存储”
START=2020-01-01 END=2020-01-07 OUT=/data/weather/point bash examples/nearest_point.sh

# 周围 50 km；radius 可修改
START=2020-01-01 END=2020-01-07 RADIUS_KM=50 OUT=/data/weather/region bash examples/region_50km.sh

# 完整参数方式；默认只下载 4 个地表天气变量
.venv/bin/python -u download_region.py wb --dataset era5 \
  --lat 36.3 --lon 120.33 --point \
  --start 2020-01-01 --end 2020-01-01 \
  --hours 0 6 12 18 --csv --out downloads/point

# 高空气压层变量
.venv/bin/python -u download_region.py wb --dataset era5 \
  --lat 36.3 --lon 120.33 --point \
  --start 2020-01-01 --end 2020-01-01 \
  --group pressure --levels 850 925 1000 --out downloads/pressure
```

日期是 **UTC** 日期且首尾包含；小时默认 00、06、12、18 UTC。起止日期必须提供，避免误下载多年。
`--point` 与 `--radius-km` 互斥。`wb` 的范围模式会保留矩形网格并将圆外的数据设为缺失值，附带距离和圆内标记。

## 大时间段、小区域：ERA5 官方 CDS

WeatherBench 无需账户，适合先验证流程。它按数据块传输，块可能覆盖全球，**保存一个点不等于只传输一个点**。
长时间的小区域下载，建议用 CDS 的服务器端区域裁剪。

1. 在 [CDS](https://cds.climate.copernicus.eu/how-to-api)注册并获得 Personal Access Token。
2. 到所需 [ERA5 单层](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels)/[气压层](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-pressure-levels)页面接受条款。
3. 在终端输入令牌后运行（令牌不显示，也不写入仓库）：

```bash
read -rsp 'CDS API token: ' CDS_API_KEY; echo
export CDS_API_KEY
.venv/bin/python -u download_region.py era5 --point \
  --lat 36.3 --lon 120.33 --start 2020-01-01 --end 2020-12-31 \
  --group surface --out /data/weather/era5
```

`--group all` 分别获取地表、13 个气压层和静态变量。CDS 输出 NetCDF；如需 CSV，下载后用 `subset --point --csv`。
ADS 使用 `ADS_API_KEY`，NASA 使用 `EARTHDATA_TOKEN`，MARS 使用 ECMWF 官方账户配置；详见[完整说明](README_zh.md)。

## 服务器上持续运行

可以使用已有的 tmux/screen，也可通过 `nohup` 将日志保存到本地：

```bash
mkdir -p logs
nohup .venv/bin/python -u download_region.py era5 --point \
  --lat 36.3 --lon 120.33 --start 2020-01-01 --end 2020-12-31 \
  --out /data/weather/era5 > logs/era5.log 2>&1 &
echo $! > logs/era5.pid
tail -f logs/era5.log
```

该命令需要已设置 `CDS_API_KEY`。已完成的请求文件会跳过；失败的 `.part` 文件下次重新下载，**不是按字节断点续传**。
同一输出目录不要同时运行相同请求。建议先按天验证，再按月或年运行。

## 已实现的数据源

| 命令 | 数据/用途 | 需要账户 |
|---|---|---|
| `download_region.py wb` | ERA5、HRES、HRES-T0、IFS ENS/Mean 的公开历史 Zarr 子集 | 否 |
| `download_region.py era5` | CDS ERA5，可服务端裁剪 | CDS |
| `download_region.py cams-eac4` / `cams-analysis` | EAC4、论文年代 CAMS 分析 | ADS |
| `download_region.py hres-mars` | 官方 HRES 历史分析场 | ECMWF MARS 权限 |
| `download_region.py gfs` | 近期 GFS NOMADS 区域数据 | 否 |
| `download_files.py esgf` | CMCC、IFS-HR 的 hist-1950 文件清单 | 搜索无需账户 |
| `download_files.py noaa` | NOAA GFS/GEFS Reforecast 档案清单 | 否 |
| `download_files.py fetch` | 按 URL 清单批量下载，包括 NASA 已生成的子集链接 | 依来源 |
| `download_region.py subset` | 已有 NetCDF/GRIB 再取最近点或附近区域 | 本地文件无需账户 |

历史 GFS 可使用 GDEX 下载清单；MERRA-2 需先在 NASA GES DISC 选择子集并导出 URL。本工具不自动替用户开通账户、创建 NASA 子集任务或获取受限档案权限。
HRES-T0 与官方 HRES Analysis 是不同产品。Climate hist-1950 不是历史逐时天气观测；近实时 GFS 接口也不能替代论文全部历史数据。

GRIB/MARS 功能可选安装：

```bash
.venv/bin/python -m pip install -r requirements-optional.txt
```

WeatherBench 内置 ERA5 store 截止 2023-01-10；脚本会检查日期覆盖，其他年份使用 CDS。不同数据集的变量、成员、气压层和许可均需核对。

## 检查与故障排查

```bash
.venv/bin/python -m unittest discover -p 'test_*.py' -v
.venv/bin/python -m pip check
.venv/bin/python download_region.py --help
.venv/bin/python download_files.py --help
.venv/bin/python download_region.py era5 --point --start 2020-01-01 --end 2020-01-01 --dry-run
```

- `--dry-run` 不提交 CDS/ADS/MARS 下载；WeatherBench 会访问远端元数据和坐标。
- `401/403`：检查相应账户令牌、数据条款和访问权限。
- `No grid centres`：范围小于网格间距，改为 `--point` 或增加半径。
- `Unavailable variables`：变量名/气压层不适用于该来源，按其目录选择。
- `No files matched`：ESGF 模式、实验、成员和时间表必须匹配；可用 `--endpoint` 切换服务节点。
- 服务器无法访问 Google/Copernicus/NASA：需要该服务器具备相应网络访问。代码不会绕过网络或账户限制。
- 不同参数生成不同文件名；不要手动改名后期望自动跳过。数据和日志目录已被 `.gitignore` 排除。

单点下载适合气象特征提取，不能直接视为预训练 Aurora 的完整空间输入。论文和预处理限制见[完整说明](README_zh.md)。

## Windows

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe download_region.py wb --point --start 2020-01-01 --end 2020-01-01 --csv
```
