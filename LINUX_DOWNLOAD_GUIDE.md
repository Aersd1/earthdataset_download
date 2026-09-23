# Linux 服务器下载指南：ERA5、GFS、ECMWF IFS

本指南用于实际下载数据的 **Linux 服务器**，不要求本地电脑安装 Linux，也不需要在本地运行下载测试。
默认目标坐标为 **东经 120.33°、北纬 36.30°**，默认最近网格点。数据下载到服务器；网页注册和接受条款可以在自己的电脑完成。

## 1. 本次使用的三个来源

| 来源参数 | 数据含义 | 账号 | 文件与时间范围 |
|---|---|---|---|
| `era5` | ERA5 再分析，历史天气重建 | 已配置的 CDS 账号 | CDS 持续更新；可从 2025 年下载至目录最新日期 |
| `gfs-archive` | GFS 0.25° 起报场和数值预报 | 不需要，包括 AWS 账号 | NOAA 公共云历史档案，按实际存在的日期下载 |
| `ifs-open` | ECMWF IFS 0.25° 开放预报子集 | 不需要，包括 AWS 账号 | ECMWF 公共 AWS 档案；逐次检查历史文件是否仍存在 |

GFS 的 `--lead-hours 0` 选择 f000 起报场；`6 12 24` 选择起报之后相应小时的预报。它不是独立下载 GDAS 产品。
IFS 这里是 `type=fc` 的开放预报，`step=0` 也是该预报产品的初始场；不是受限 MARS 完整高分辨率分析档案，也不是 Aurora 自身的预报输出。
IFS 官网保留近期滚动档案；本工具使用可能保留较早文件的 AWS 副本。不能保证每个历史日期都仍然存在，缺失会报错，程序不会把缺失日期当成成功。

## 2. 在 Linux 服务器安装或更新

首次使用：

```bash
git clone https://github.com/Aersd1/earthdataset_download.git
cd earthdataset_download
bash setup.sh
.venv/bin/python -m pip install -r requirements-forecast.txt
```

已经克隆过仓库：

```bash
cd /你的仓库路径/earthdataset_download
git pull --ff-only
bash setup.sh
.venv/bin/python -m pip install -r requirements-forecast.txt
```

需要 Python 3.11 或更高版本；如果默认 `python3` 较旧，可以使用 `PYTHON_BIN=python3.12 bash setup.sh`。
`setup.sh` 默认只安装环境，不提交数据请求，也不运行测试。可选 `RUN_TESTS=1 bash setup.sh` 才运行离线测试。
GFS/IFS 的 GRIB 解码需要 `cfgrib` 与 `eccodes`，由 `requirements-forecast.txt` 安装。若特定 Linux 架构缺少可用 ecCodes 二进制依赖，可在已有 Conda 环境用 `conda install -c conda-forge eccodes cfgrib`，并使用该环境的 Python 执行后续命令。

## 3. ERA5 账号已配置，接下来做什么

程序读取服务器上的 `~/.cdsapirc`，配置格式是：

```yaml
url: https://cds.climate.copernicus.eu/api
key: <你的 Personal Access Token>
```

**已有正确配置不需要重填。** 还支持 `CDS_API_KEY` 环境变量（优先读取）和 `CDSAPI_RC` 指定配置文件。
电脑浏览器登录成功，不代表另一台服务器已有配置；这里指的是实际下载服务器上的文件或环境变量。

可选检查命令，不显示 token，不发起下载：

```bash
.venv/bin/python setup_account.py cds --check
```

出现 `Local token configured ...` 表示本机找到了配置，**不代表远端授权或数据条款已经核验成功**。
如果配置缺失，运行 `.venv/bin/python setup_account.py cds`，在隐藏输入中粘贴 token；工具保存到用户目录，不写入 Git 仓库。

还需在浏览器手动接受数据条款：

- [ERA5 单层数据下载页](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download)：地表/静态变量。
- [ERA5 气压层数据下载页](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-pressure-levels?tab=download)：高空气压层变量。
- [CDS API 配置页](https://cds.climate.copernicus.eu/how-to-api)：查看自己的 token 与官方配置说明。

条款在下载表单底部。选用哪类数据就接受对应数据集的条款；不需要为了 API 下载在网页上反复手工选择年月日。
缺少 token 或遇到 401/403 时，程序会显示需要访问的链接和下一步操作。在有桌面浏览器的机器上会尝试打开页面；无桌面的 Linux 服务器会输出网址，供你在自己电脑上打开。
手动显示这些网页：`.venv/bin/python download_region.py era5 --open-registration`。

## 4. 日期怎么写

三个来源都使用相同语法。日期用连字符，月份和日补零，均为 **UTC**，包含起止日。

| 参数 | 实际选择 |
|---|---|
| `--date 2025` | 2025 全年 |
| `--date 2025-03` | 2025 年 3 月整月 |
| `--date 2025-03-15` | 2025-03-15 当天 |
| `--start 2025 --end 2026-02` | 2025-01-01 至 2026-02-28 |
| `--start 2025-03 --end 2025-06-15` | 2025-03-01 至 2025-06-15 |
| `--start 2025` | 2025-01-01 至该来源最新可用日期 |

`--date` 不能与 `--start/--end` 同时使用；年/月作为开始时补第一天，作为结束时补最后一天，自动处理闰年。
`--date 2026` 代表完整 2026 年；若要“2026 年至今”，请用 `--start 2026`。指定了未来尚未发布的完整范围时，程序不会悄悄截短成部分数据。

省略 `--end` 的规则：

- ERA5 读取实时 CDS 目录，不硬编码“今天减 5 天”。`--group all` 取单层和气压层共同覆盖的最新日期。目录是集合级覆盖，个别变量或小时是否已发布仍由源接口核验。
- GFS/IFS 检查最近 5 天内所选全部起报时刻和预报提前量的文件及索引，取最新完整的一天。如果你只需要每天 00 UTC，就用 `--hours 0`，避免等待 18 UTC 的产品全部发布。
- 遇到网络错误、限流或查不到完整日期时明确报错，不猜一个截止日期，也不会把“今天”直接作为可用日期。
- “自动截止”每次启动查询一次；这不是定时监控服务。以后重新执行相同 `--start` 可继续获取新增数据。

**ERA5 的日期是数据日期；GFS/IFS 的日期是起报日期。** 例如 `--date 2025-01-01 --hours 12 --lead-hours 24` 是 1 月 1 日 12 UTC 发布的、预报 1 月 2 日 12 UTC 的场。即使结束日期是 1 月 1 日，也会包含其预报有效时间延伸到之后的结果。

## 5. ERA5 下载命令

下面都使用已配置账号。默认下载 2 米气温、10 米东西风/南北风、海平面气压，时刻为 00/06/12/18 UTC。

```bash
# 先下载一天；用于在实际 Linux 服务器核验账号、条款和输出
.venv/bin/python -u download_region.py era5 --nearest --date 2025-01-01 \
  --lat 36.3 --lon 120.33 --out downloads/era5

# 整年、整月、混合精度的起止范围
.venv/bin/python -u download_region.py era5 --nearest --date 2025 --out downloads/era5
.venv/bin/python -u download_region.py era5 --nearest --date 2025-03 --out downloads/era5
.venv/bin/python -u download_region.py era5 --nearest --start 2025 --end 2026-02 --out downloads/era5

# 从 2025 年到最新可用日期
.venv/bin/python -u download_region.py era5 --nearest --start 2025 --out downloads/era5

# 如果需要每小时，而不是默认每 6 小时
.venv/bin/python -u download_region.py era5 --nearest --date 2025-03 \
  --hours {0..23} --out downloads/era5_hourly

# 只下载风速分量；风速大小可由 sqrt(u^2 + v^2) 计算
.venv/bin/python -u download_region.py era5 --nearest --start 2025 \
  --variables 10m_u_component_of_wind 10m_v_component_of_wind --out downloads/era5_wind
```

`--group pressure --levels 850 925 1000` 可选择高空变量；`--group all` 获取预设地表、气压层和静态变量。
请求按月分批提交，ERA5 输出 NetCDF 与请求 JSON。若还需 CSV，可对已下载单点文件执行 `subset`，使用实际最近格点坐标：

```bash
.venv/bin/python download_region.py subset --input /实际文件路径/era5文件.nc \
  --nearest --lat 36.25 --lon 120.25 --csv --out downloads/era5_csv
```

## 6. GFS 分析与预报

**2025 年起的历史范围使用 `gfs-archive`**；旧命令 `gfs` 使用 NOMADS，仅适用于近期滚动数据。
下面下载公共 AWS 档案，无需注册。

```bash
# f000 起报场：一天、每天四个起报时刻
.venv/bin/python -u download_region.py gfs-archive --nearest --date 2025-01-01 \
  --hours 0 6 12 18 --lead-hours 0 --csv --out downloads/gfs_analysis

# 2025 年至最新：起报场
.venv/bin/python -u download_region.py gfs-archive --nearest --start 2025 \
  --hours 0 6 12 18 --lead-hours 0 --csv --out downloads/gfs_analysis

# 2025 年至最新：每天 00/12 UTC 起报，6、12、24 小时预报
.venv/bin/python -u download_region.py gfs-archive --nearest --start 2025 \
  --hours 0 12 --lead-hours 6 12 24 --csv --out downloads/gfs_forecast

# 指定整月，只获取地表风速分量
.venv/bin/python -u download_region.py gfs-archive --nearest --date 2025-03 \
  --hours 0 12 --lead-hours 0 6 12 24 --variables UGRD VGRD --csv --out downloads/gfs_wind
```

GFS 变量名使用 `UGRD VGRD TMP PRMSL` 等，不能直接使用 ERA5 的长变量名。
默认地表选择 10 米风、2 米气温、海平面气压；压力层示例：`--group pressure --levels 850 925 1000 --variables UGRD VGRD TMP`。
GFS 的 `HGT` 是位势高度，和 ERA5 的 `geopotential` 单位不同，不能直接拼接当作同一个量。

## 7. ECMWF IFS 开放预报

```bash
# 一天的开放预报，包含 step=0 初始场及 6/12/24 小时预报
.venv/bin/python -u download_region.py ifs-open --nearest --date 2025-01-01 \
  --hours 0 12 --lead-hours 0 6 12 24 --csv --out downloads/ifs

# 从 2025 年到最新可用起报日期
.venv/bin/python -u download_region.py ifs-open --nearest --start 2025 \
  --hours 0 12 --lead-hours 0 6 12 24 --csv --out downloads/ifs

# 指定起止年月，只取 10 米风
.venv/bin/python -u download_region.py ifs-open --nearest --start 2025-03 --end 2025-06 \
  --hours 0 12 --lead-hours 6 12 24 --variables 10u 10v --csv --out downloads/ifs_wind

# 历史开放产品的高空层次，显式选择可用层
.venv/bin/python -u download_region.py ifs-open --nearest --date 2025-03-01 \
  --hours 0 12 --lead-hours 0 6 12 24 --group pressure \
  --levels 50 200 250 300 500 700 850 925 1000 --variables t u v q gh --out downloads/ifs_pressure
```

默认地表参数为 `2t 10u 10v msl`。开放产品不同年份提供的参数、层次和最大预报时效可能变化，不能假定最新参数在 2025 年也存在。`gh` 是位势高度；要求其他变量时应先查看当期产品索引。
06/18 UTC 在旧目录中可能使用 `scda`，新版使用 `oper`；脚本查找两种目录。使用 00/12 UTC 的示例便于跨年份统一。
本工具不下载集合成员、AIFS 或波浪产品；也不会转用付费档案补齐缺失历史日期。

## 8. 最近点、附近范围和传输量

三个来源均支持：

```bash
--lat 36.3 --lon 120.33 --nearest
--lat 36.3 --lon 120.33 --radius-km 50
```

两种空间方式互斥。`--nearest` 等同于 `--point`，取实际网格最近点，不插值。0.25° 常规网格下本坐标对应约 **120.25°E、36.25°N**。
ERA5 请求服务器端区域裁剪；半径模式返回包含圆的矩形。GFS/IFS 先按索引下载选中变量和层次的完整 GRIB 消息，再在服务器本地提取最近点或圆形范围（圆外网格设为缺失）。同一消息中耦合存储的字段可能一起保留。
因此 GFS/IFS 的网络流量仍可能很大，最终只有一个点不代表网络只下载一个点。首次可只选一天、一个起报时刻、一个提前量，再扩大范围。

GFS/IFS 每个起报时刻、提前量生成独立文件，异构高度/层次可能拆成多个 `partNN.nc`，可选 `--csv` 同时输出 CSV。文件保留 `time`、`step`、`valid_time` 等源坐标和起报信息，不能只按有效时间合并而丢掉预报提前量。
默认清理该次下载的临时全球 GRIB 字段，只保留区域输出；`--keep-grib` 可保留 GRIB。请求 JSON 记录实际来源 URL、选中字段和完成文件列表。

## 9. 后台下载、日志和恢复

```bash
mkdir -p logs
nohup .venv/bin/python -u download_region.py era5 --nearest --start 2025 \
  --out downloads/era5 > logs/era5.log 2>&1 &
echo $! > logs/era5.pid

nohup .venv/bin/python -u download_region.py gfs-archive --nearest --start 2025 \
  --hours 0 12 --lead-hours 0 6 12 24 --out downloads/gfs > logs/gfs.log 2>&1 &
echo $! > logs/gfs.pid

nohup .venv/bin/python -u download_region.py ifs-open --nearest --start 2025 \
  --hours 0 12 --lead-hours 0 6 12 24 --out downloads/ifs > logs/ifs.log 2>&1 &
echo $! > logs/ifs.pid

tail -f logs/era5.log
```

可以只运行需要的那一条，也可以分开运行三条。中断后重新执行同一命令：已完成的相同请求会跳过，未完成文件重新下载；不是按字节断点续传。
ERA5 截止日期推进时，最后一个未满月的请求会重新生成，先前结果保留。程序不会自动用最终 ERA5 替换已保存的 ERA5T，若需最终版本应在新输出目录重新下载对应月份。
不要在同一输出目录同时启动完全相同的任务。

## 10. 查看请求与故障提示

在服务器上可以先添加 `--dry-run`。ERA5 不提交下载请求；若省略截止日仍会查询最新目录。GFS/IFS 会读取索引，不下载 GRIB 数据。

| 提示 | 操作 |
|---|---|
| token 未配置 | 确认 Linux 服务器上的 `~/.cdsapirc`，或运行 `setup_account.py cds` |
| ERA5 401/403 | 检查 token、对应数据条款、账号权限；程序会给出网页 |
| 404 / archive missing | 对应日期、起报时刻或预报提前量不在公开档案；核对后缩小范围，不代表需要注册 |
| 429 / 503 | 数据源限流或暂不可用，程序对部分服务端错误重试；稍后重跑可以跳过已完成请求 |
| Cannot read latest availability | 最新日期查询失败；修复网络后重试，或显式提供已知可用的 `--end` |
| IFS pressure levels absent | 按该年的开放层次显式设置 `--levels` |
| ecCodes/cfgrib 缺失 | 安装 `requirements-forecast.txt`；特殊 Linux 平台使用兼容的 Conda 包 |

本次新增下载路径未在用户的 Linux 服务器进行端到端验证。按用户要求，不继续在本地 Windows 电脑运行测试或实际下载；上述一天样例供在实际服务器首次运行。

## 官方来源

- [CDS API 配置与条款要求](https://cds.climate.copernicus.eu/how-to-api)
- [ERA5 数据目录](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels)
- [NOAA GFS 公共 AWS 档案](https://registry.opendata.aws/noaa-gfs-bdp-pds/)
- [NOAA GRIB 索引与 HTTP 部分下载说明](https://www.cpc.ncep.noaa.gov/products/wesley/fast_downloading_grib.html)
- [ECMWF IFS 开放数据说明](https://www.ecmwf.int/en/forecasts/datasets/open-data)
- [ECMWF 公共 AWS 副本](https://registry.opendata.aws/ecmwf-forecasts/)
- [ECMWF 官方客户端及索引格式实现](https://github.com/ecmwf/ecmwf-opendata)
