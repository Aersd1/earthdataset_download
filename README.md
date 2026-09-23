# Earth dataset downloader

Aurora 论文数据集下载工具，支持**最近网格点**和**坐标附近区域**。可独立运行于 Linux 服务器，不依赖原来的 Windows 工作目录，也不需要 GPU。

默认位置 **120.33°E、36.30°N**，所有参数均可修改。[完整数据集清单和各来源操作说明](README_zh.md)。

**本次优先下载 ERA5、GFS 分析与预报、ECMWF IFS 开放预报：请直接阅读 [Linux 服务器完整下载指南](LINUX_DOWNLOAD_GUIDE.md)。** 包含已配置账号后的操作、年/月/日与自动截止日期、三个来源的命令、后台日志和故障提示。

## 已在 Linux 配置好 ERA5 账号：直接使用

在实际下载服务器的仓库目录执行：

```bash
git pull --ff-only
bash setup.sh
# 只检查本机配置是否存在，不显示 token，也不提交下载
.venv/bin/python setup_account.py cds --check
# 先验证一天；会真正检查账号、条款和下载链路
DATE=2025-01-01 bash examples/era5_linux.sh
# 从 2025 年初到官方目录当前最新可用日期
START=2025 bash examples/era5_linux.sh
```

脚本自动读取 Linux 的 `~/.cdsapirc`，也支持 `CDSAPI_RC` 指定文件；`CDS_API_KEY` 环境变量优先于文件。已有配置无需重新输入 token。
`setup_account.py --check` 只验证本机配置，**不会宣称服务器已授权**；必须用一天的真实下载核验账号和条款。
未接受条款时，到 [ERA5 单层下载页](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download)底部手动接受；气压层需要在其页面单独接受。

## 年、月、日与起止时间

以下参数适用于 `download_region.py`，时间均为 UTC，包含开始和结束日期。`--date` 与 `--start/--end` 不能同时使用。

| 写法 | 含义 |
|---|---|
| `--date 2025` | 2025-01-01 至 2025-12-31 |
| `--date 2025-02` | 2025-02-01 至 2025-02-28（自动处理闰年） |
| `--date 2025-02-03` | 当天 |
| `--start 2025 --end 2026-02` | 2025-01-01 至 2026-02-28 |
| `--start 2025-03 --end 2025-06-15` | 2025-03-01 至 2025-06-15 |
| `--start 2025` | 2025-01-01 至该数据源最新可用日期 |

```bash
.venv/bin/python -u download_region.py era5 --nearest --date 2025-03
.venv/bin/python -u download_region.py era5 --nearest --start 2025 --end 2026-02
.venv/bin/python -u download_region.py era5 --nearest --start 2025 --out /data/weather/era5
# 只展示范围和请求，不提交数据下载（自动截止时间仍要联网查元数据）
.venv/bin/python download_region.py era5 --nearest --start 2025 --dry-run
```

`--start` 的年/月补为第一天，`--end` 的年/月补为最后一天。**`--date 2026` 表示完整 2026 年；若想“2026 年至今”，使用 `--start 2026`。**
明确指定的范围不会静默截短；如果其中数据尚未发布，由源接口报错。省略截止时间时：

- ERA5 / CAMS：读取官方目录实时覆盖范围；ERA5 `--group all` 取单层和气压层共同的最新日期。查询失败即报错，不猜测今天或固定延迟。目录日期是集合级覆盖，并不保证每个变量/小时都已发布；源接口仍会校验。
- WeatherBench：从所选 store 的实际时间坐标读最后一天，其历史数据不会因为当前年份变化而延长。
- GFS NOMADS：检查最近 5 天中所有所选起报时刻和预报时效是否存在，取最新完整的一天；仍仅适用于近期滚动档案。
- GFS 公共档案 `gfs-archive` 与 IFS 开放预报 `ifs-open`：支持历史日期，省略截止日时检查公共档案近期所选起报时刻/提前量的文件与索引，取最新完整日。使用方法见 [Linux 指南](LINUX_DOWNLOAD_GUIDE.md)。
- 本地 `subset`：不填开始/结束时，保留文件该方向上全部可用时间。
- 受限 `hres-mars` 没有可用的公开最新日期目录，必须显式给出 `--end`。`cams-analysis` 仍限定论文年代、2023-06-27 以前；日期解析功能不改变这一产品限制。

Linux 简写脚本支持 `DATE`，或 `START` 加可选 `END`，以及 `LAT/LON/GROUP/OUT/PYTHON_BIN`。默认地点为本项目坐标、最近点、地表变量、每天 00/06/12/18 UTC；需每小时数据时在命令后加 `--hours {0..23}`。按月分请求，重复运行会跳过已完成的相同文件；新截止日期会使最后一个未满月请求重新生成。

```bash
DATE=2025 bash examples/era5_linux.sh
START=2025-03 END=2025-06 OUT=/data/weather/era5 bash examples/era5_linux.sh
# 每小时数据（Bash 展开 0 到 23），自定义变量
DATE=2025-03 bash examples/era5_linux.sh --hours {0..23} --variables 10m_u_component_of_wind 10m_v_component_of_wind
```

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

日期是 **UTC** 日期且首尾包含；小时默认 00、06、12、18 UTC。区域下载需提供 `--date` 或 `--start`；`--end` 可以省略，规则见上方。
`--point` 与 `--radius-km` 互斥。`wb` 的范围模式会保留矩形网格并将圆外的数据设为缺失值，附带距离和圆内标记。

## 大时间段、小区域：ERA5 官方 CDS

WeatherBench 无需账户，适合先验证流程。它按数据块传输，块可能覆盖全球，**保存一个点不等于只传输一个点**。
长时间的小区域下载，建议用 CDS 的服务器端区域裁剪。

1. 在 [CDS](https://cds.climate.copernicus.eu/how-to-api)注册并获得 Personal Access Token。
2. 到所需 [ERA5 单层](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels)/[气压层](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-pressure-levels)页面接受条款。
3. 已有 `~/.cdsapirc` 时直接下载。首次配置可以运行下面的交互工具，令牌输入不回显，写到 Linux 用户目录、权限为 600，不进入仓库：

```bash
.venv/bin/python setup_account.py cds
.venv/bin/python -u download_region.py era5 --point \
  --lat 36.3 --lon 120.33 --start 2025 \
  --group surface --out /data/weather/era5
```

`--group all` 分别获取地表、13 个气压层和静态变量。CDS 输出 NetCDF；如需 CSV，下载后用 `subset --point --csv`。
ADS 使用 `ADS_API_KEY`，NASA 使用 `EARTHDATA_TOKEN`，MARS 使用 ECMWF 官方账户配置；详见[完整说明](README_zh.md)。
ADS 也支持 `python setup_account.py ads` 写入独立的 `~/.adsapirc`，避免覆盖 CDS 配置。

需要账号时程序会给出注册/API 页面、条款页面与下一步操作；支持桌面的机器可尝试自动打开浏览器，无桌面的 Linux 服务器会打印链接供你在个人电脑打开。仅缺少本机 token 或遇到 401/403 时触发提醒，无法替你判断或接受条款。

```bash
.venv/bin/python download_region.py era5 --open-registration
.venv/bin/python setup_account.py cds --check --open
# 其他需要账号的来源：显示相应页面和要求
.venv/bin/python setup_account.py ads --open
.venv/bin/python setup_account.py earthdata --open
.venv/bin/python setup_account.py mars --open
```

## 服务器上持续运行

可以使用已有的 tmux/screen，也可通过 `nohup` 将日志保存到本地：

```bash
mkdir -p logs
nohup .venv/bin/python -u download_region.py era5 --point \
  --lat 36.3 --lon 120.33 --start 2025 \
  --out /data/weather/era5 > logs/era5.log 2>&1 &
echo $! > logs/era5.pid
tail -f logs/era5.log
```

该命令需要已有 `~/.cdsapirc` 或设置 `CDS_API_KEY`。已完成的请求文件会跳过；失败的 `.part` 文件下次重新下载，**不是按字节断点续传**。
同一输出目录不要同时运行相同请求。建议先按天验证，再按月或年运行。

## 已实现的数据源

| 命令 | 数据/用途 | 需要账户 |
|---|---|---|
| `download_region.py wb` | ERA5、HRES、HRES-T0、IFS ENS/Mean 的公开历史 Zarr 子集 | 否 |
| `download_region.py era5` | CDS ERA5，可服务端裁剪 | CDS |
| `download_region.py gfs-archive` | NOAA 公共历史 GFS 起报场/预报，筛选字段后取最近点/区域 | 否 |
| `download_region.py ifs-open` | ECMWF AWS 公开 IFS 0.25° 确定性预报子集 | 否 |
| `download_region.py cams-eac4` / `cams-analysis` | EAC4、论文年代 CAMS 分析 | ADS |
| `download_region.py hres-mars` | 官方 HRES 历史分析场 | ECMWF MARS 权限 |
| `download_region.py gfs` | 近期 GFS NOMADS 区域数据 | 否 |
| `download_files.py esgf` | CMCC、IFS-HR 的 hist-1950 文件清单 | 搜索无需账户 |
| `download_files.py noaa` | NOAA GFS/GEFS Reforecast 档案清单 | 否 |
| `download_files.py fetch` | 按 URL 清单批量下载，包括 NASA 已生成的子集链接 | 依来源 |
| `download_region.py subset` | 已有 NetCDF/GRIB 再取最近点或附近区域 | 本地文件无需账户 |

历史 GFS 优先使用 `gfs-archive`，也可使用 GDEX 下载清单；MERRA-2 需先在 NASA GES DISC 选择子集并导出 URL。本工具不自动替用户开通账户、创建 NASA 子集任务或获取受限档案权限。
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
