# Aurora v2 数据集与按坐标下载

核对日期：2026-09-23。对象是用户指定的 [arXiv 2405.13063v2](https://arxiv.org/html/2405.13063v2)，不是之后扩展任务的版本。

**Linux 最新用法：** 已配置 ERA5 的 `~/.cdsapirc` 可直接使用。新增 `--date 2025` / `--date 2025-03` / `--date 2025-03-01`，或 `--start 2025 --end 2026-02`；省略 `--end` 时查询源的最新可用日期。完整规则、账号提醒、Linux 示例见 [README](README.md)。本页保留的历史日期用于复现论文，不表示数据源的当前截止日期。
目标坐标：**120.33°E、36.30°N**。尚未指定时间段；下面的 2020-01-01 只是小样本示例。

## 1. 论文到底用了哪些数据

主模型预训练使用 ERA5、CMCC、IFS-HR、HRES Forecasts、GFS Analysis、GFS Forecasts 六类。
附录表 3 的十个数据集是各预训练配置/数据扩展实验的总清单，不能理解成主模型同时用完十个数据集。
以下年份、分辨率表示论文所用版本/处理结果，不等于当前官网全部可用年份和原生网格。来源：[论文 §2、附录 C、表 3–5](https://arxiv.org/html/2405.13063v2)。

| 数据 | 论文预训练时间 | 论文网格 | 下载路径 / 本工具 |
|---|---|---|---|
| ERA5 | 1979–2020 | 0.25° | CDS：`era5`；WeatherBench：`wb --dataset era5` |
| HRES Forecasts / HRES-0.25 | 2016–2020 | 0.25° | WeatherBench：`wb --dataset hres` |
| IFS-ENS-0.25 | 2018–2020 | 0.25° | WeatherBench：`wb --dataset ifs-ens` |
| GFS Forecast | 2015–2020 | 0.25° | NCAR GDEX 历史档案；近期使用 `gfs` |
| GFS Analysis / GFS-T0 | 2015–2020 | 0.25° | 同 GFS 档案，取预报时效 f000 |
| GEFS Reforecast | 2000–2019 | 0.25° | NOAA GEFSv12 retrospective：`download_files.py noaa` |
| CMCC-CM2-VHR4 | 1950–2014 | 0.25° | ESGF HighResMIP / hist-1950：`download_files.py esgf` |
| ECMWF-IFS-HR | 1950–2014 | 0.45° | ESGF / CEDA，同上 |
| MERRA-2 | 1980–2020 | 经度 0.625° × 纬度 0.5° | NASA GES DISC 导出下载清单，再 `download_files.py fetch` |
| IFS-ENS-Mean | 2018–2020 | 0.25° | WeatherBench：`wb --dataset ifs-ens-mean` |

微调还使用 HRES-0.25（2016–2021）、HRES-0.1（2016–2022）、CAMSRA/EAC4（2003–2021，0.75°）、CAMS Analysis（2017-10 至 2022-05，0.4°）。评估包括 HRES、CAMS，以及 NOAA ISD 站点观测。CAMS 测试日期正文与表格表述有差异，复现时以附录表 5 的 2022-06 至 2022-11 及具体实验定义核对。

天气变量核心为 2 m 温度、10 m 的 U/V 风、海平面气压；高空为 U/V 风、温度、比湿、位势。
常用气压层为 50、100、150、200、250、300、400、500、600、700、850、925、1000 hPa。
部分数据不具备全部变量/气压层；IFS ENS 仅 500/700/850 hPa，气候模拟和 GEFS 也需按原数据核对。

## 2. 能只下载坐标或附近吗

**可以。** 本工具提供：

- `--point`：取最近原始网格点，不插值。ERA5 对该坐标返回 **120.25°E、36.25°N**，距离约 **9.07 km**。
- `--radius-km 50`：以目标坐标为中心取附近数据；默认半径 50 km。

| 来源 | 服务器端裁剪 / 实际传输 | 最近点实现 |
|---|---|---|
| ERA5 CDS | 支持 `area=[北,西,南,东]`，无需下载全球 | 对齐 0.25° 网格后提交单点 area |
| CAMS ADS | 支持区域；此脚本请求论文年代网格 | EAC4 按 0.75°，历史 CAMS 按 0.4° 对齐 |
| HRES MARS | 有档案访问权限时可指定 area/grid | 对齐请求的 0.1° 或 0.25° 输出网格 |
| WeatherBench Zarr | 只读取所选时刻/变量所需数据块，但块可能覆盖全球 | 用坐标索引取最近网格；输出很小不代表网络流量也很小 |
| 近期 GFS NOMADS | 支持服务器端区域筛选 | 先下载小矩形，再 `subset --point` |
| CMIP6、GFS/GEFS 历史整文件 | 普通 HTTPS 下载不支持空间切片 | 整文件下载后裁剪；节点若提供 OPeNDAP/NCSS 可另用其子集服务 |
| MERRA-2 | GES DISC Subsetter / OPeNDAP 支持区域和变量子集 | 在官方子集服务选小区域，再取最近点 |
| ISD | 是离散站点，不是规则网格 | 选最近站点，不等同于最近模式网格点 |

CDS/ADS/MARS/NOMADS 的 radius 参数生成**包围圆形区域的矩形**，所以边角可能超出 50 km。
`wb` 和 `subset` 会进一步计算球面距离、写入 `distance_km` 和 `within_radius`，圆外数值设为缺失值。
`--point` 与 `--radius-km` 互斥。纬度允许 [-90,90]、经度 [-180,180]；跨越 ±180° 的区域明确报错，需要分两次请求。当前只支持一维规则经纬度轴，不支持二维曲线网格。

这里的最近点按规则网格经纬度分别取最近索引，经度考虑周期性；这是网格采样，不是站点观测，也不产生精确坐标上的新观测。

## 3. 安装与最快验证

在克隆后的仓库根目录运行。以下默认 Linux；Windows 命令见 README.md：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

新服务器需要先安装依赖。无需账户的 ERA5 最近点例子：

```bash
.venv/bin/python download_region.py wb --dataset era5 --lat 36.3 --lon 120.33 --point --start 2020-01-01 --end 2020-01-01 --csv --out downloads/my_point
```

周围 50 km：

```bash
.venv/bin/python download_region.py wb --dataset era5 --lat 36.3 --lon 120.33 --radius-km 50 --start 2020-01-01 --end 2020-01-01 --out downloads/my_region
```

所有时间为 **UTC**；默认 00/06/12/18 UTC，`--hours 0 6` 可修改。中国北京时间为 UTC+8。
默认仅下载四个地表天气变量，不会自动下载所有高空层。
按月分文件，文件名包含请求指纹，避免不同坐标/变量意外复用已有文件；完成文件可跳过，失败保留 `.part` 并在下次重下。
`--dry-run` 只查看请求；WeatherBench 会读取远端元数据/坐标以确认实际范围，不写数据文件。

## 4. 长时间、小区域首选 ERA5 CDS

官方入口：[单层 ERA5](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels)、[气压层 ERA5](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-pressure-levels)、[API 配置](https://cds.climate.copernicus.eu/how-to-api)。

注册 CDS，在对应数据集下载页接受条款，然后将自己的 Personal Access Token 放入当前终端环境变量；不要写进脚本或提交到仓库：

```bash
read -rsp 'CDS API token: ' CDS_API_KEY; echo
export CDS_API_KEY
.venv/bin/python download_region.py era5 --point --start 2020-01-01 --end 2020-12-31 --group surface
```

只看请求无需令牌：

```bash
.venv/bin/python download_region.py era5 --point --start 2020-01-01 --end 2020-01-01 --group all --dry-run
```

`--group all` 包含地表、13 个高空气压层、静态地表位势/海陆掩膜/土壤类型，分开请求。
`--group pressure --levels 850 925 1000` 可减少高空数据。
`--variables 100m_u_component_of_wind 100m_v_component_of_wind` 可请求 ERA5 的 100 m 风，但它们是风电任务可选扩展，并不是这篇论文的四个默认地表变量。
按小时下载可加 `--hours 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23`。

CDS 请求中的 area 已对齐最近网格；范围请求保留矩形。如需距离字段、精确圆形掩膜或 CSV，用下面第 9 节进一步整理文件。

## 5. HRES / IFS ENS：WeatherBench 与官方分析场分开

[WeatherBench 官方数据说明](https://weatherbench2.readthedocs.io/en/latest/data-guide.html)列出了公开 Zarr。
工具内置的 ERA5 store 实际截止 **2023-01-10**，HRES 以 store 坐标为准；超出范围会报错而不是静默输出部分日期。

```bash
# HRES 预报：time 是起报时间，lead-hours 是预报时效
.venv/bin/python download_region.py wb --dataset hres --point --start 2020-01-01 --end 2020-01-01 --hours 0 12 --lead-hours 0 6 12 24 --csv

# HRES-T0（预报初始化状态）
.venv/bin/python download_region.py wb --dataset hres-t0 --point --start 2020-01-01 --end 2020-01-01 --csv

# IFS 集合的指定成员；不要无意间下载全部成员和全部时效
.venv/bin/python download_region.py wb --dataset ifs-ens --point --start 2020-01-01 --end 2020-01-01 --hours 0 --members 1 2 --lead-hours 0 6 12

# 集合平均
.venv/bin/python download_region.py wb --dataset ifs-ens-mean --point --start 2020-01-01 --end 2020-01-01 --hours 0 --lead-hours 0 6 12
```

高空变量可加 `--variables temperature u_component_of_wind --levels 500 700 850`。
检查各数据集自己的许可，特别是 TIGGE 来源的集合资料。

**HRES-T0 ≠ HRES official analysis**。论文高分辨率微调所用的官方分析场需要对应 ECMWF 历史档案权限；不能用免费实时预报或 ERA5 冒充。[ECMWF 档案入口](https://www.ecmwf.int/en/forecasts/access-forecasts/access-archive-datasets)、[MARS API](https://confluence.ecmwf.int/spaces/WEBAPI/pages/47293600/Access+MARS)。

```bash
.venv/bin/python -m pip install ecmwf-api-client
# 按 ECMWF 官方说明配置 .ecmwfapirc 且拥有 MARS 权限后，移除 --dry-run
.venv/bin/python download_region.py hres-mars --point --start 2020-01-01 --end 2020-01-01 --grid 0.1 --group surface --dry-run
```

此适配器请求 `class=od, stream=oper, type=an`。MARS grid 表示归一到指定经纬度输出网格，不意味着模式本身的原生网格就是该规则网格。

## 6. CAMS 与 CAMSRA/EAC4

入口：[EAC4](https://ads.atmosphere.copernicus.eu/datasets/cams-global-reanalysis-eac4)、[CAMS](https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts)、[ADS API](https://ads.atmosphere.copernicus.eu/how-to-api)。ADS 的令牌和 CDS 的令牌分别配置。

```bash
read -rsp 'ADS API token: ' ADS_API_KEY; echo
export ADS_API_KEY
.venv/bin/python download_region.py cams-eac4 --point --start 2020-01-01 --end 2020-01-02 --hours 0 12 --variables total_column_carbon_monoxide particulate_matter_2.5um
.venv/bin/python download_region.py cams-analysis --point --start 2020-01-01 --end 2020-01-02 --hours 0 12 --variables total_column_carbon_monoxide particulate_matter_2.5um
```

高空气体示例：`--group pressure --variables carbon_monoxide ozone --levels 500 850`。
默认输出 GRIB，避免不同 ADS NetCDF 打包格式混淆。
`cams-analysis` 明确请求 `type=analysis, leadtime_hour=0`，依据 [CAMS 官方文档](https://confluence.ecmwf.int/pages/viewpage.action?pageId=673323626)；不会把普通 forecast 自动当作 analysis。
该预设只覆盖 2023-06-27 之前的论文年代网格。变量/气压层组合并非所有年代都可用，应以 ADS 表单和产品说明为准。不同物种的地表总柱量、地表浓度、高空质量混合比不能混用。

## 7. GFS / GEFS 历史与近期下载

论文年代 GFS 首先查询 [NCAR GDEX d084001（原 ds084.1）](https://gdex.ucar.edu/datasets/d084001/)，该档案包含 2015 年以来的 0.25° GFS。
在网站选时间、cycle 和 f000/f006 等时效，导出 HTTPS 下载链接清单 `gfs_urls.txt`，再执行：

```bash
.venv/bin/python download_files.py fetch --manifest gfs_urls.txt --out downloads/gfs_history
```

`f000` 对应这里的 GFS-T0；其他时效是预测。不要把 GFS 预报有效时间与起报时间混淆。GDEX 访问/子集服务若要求登录，请使用其网站提供的已授权链接或下载工具。

[NOAA GFS 公共桶](https://registry.opendata.aws/noaa-gfs-bdp-pds/)也能检索，但应检查实际 key 是否存在，不能假设当前公共桶完整覆盖 2015–2020。示例只生成清单：

```bash
.venv/bin/python download_files.py noaa --bucket noaa-gfs-bdp-pds --prefix gfs.20200101/00/ --contains pgrb2.0p25.f000 --out downloads/gfs_manifest.jsonl
```

如果返回 0 个文件，表示该前缀没有对象，改用 GDEX 历史档案。

GEFS 必须用 [GEFS **Reforecast** 桶](https://registry.opendata.aws/noaa-gefs-reforecast/)，不是当前实时 GEFS：

```bash
.venv/bin/python download_files.py noaa --bucket noaa-gefs-retrospective --prefix GEFSv12/reforecast/2000/2000010100/c00/ --contains ugrd_pres --out downloads/gefs_manifest.jsonl
.venv/bin/python download_files.py fetch --manifest downloads/gefs_manifest.jsonl --out downloads/gefs --dry-run
```

查看清单并保留所需的变量文件，去掉 `--dry-run` 才下载。一个变量文件也可能达到数百 MB；普通 HTTPS 整文件不会因最终取一个点而减小。
GEFS 通常每日 5 个成员，部分周运行更多；不同预报时效、层次可能采用不同分辨率，见 [NOAA 存储说明](https://noaa-gefs-retrospective.s3.amazonaws.com/Description_of_reforecast_data.pdf)。

只要近期 GFS 时，可使用 NOMADS 的服务端区域过滤（日期替换为当前仍在服务器上的日期）：

```bash
.venv/bin/python download_region.py gfs --radius-km 50 --start 2026-09-22 --end 2026-09-22 --hours 0 --lead-hours 0 6 12 --dry-run
```

根据 [NOMADS](https://nomads.ncep.noaa.gov/)实际可用目录修改日期，去掉 `--dry-run` 执行。近期接口不能下载论文全部历史训练年份。GRIB 下载完成后可再提取最近点。

## 8. CMIP6 与 MERRA-2

CMIP6 必须选 **HighResMIP / hist-1950**，不能随意替换成 historical、SSP 或其他同名模式产品。
原始来源：[CMCC DOI](https://doi.org/10.22033/ESGF/CMIP6.3818)、[IFS-HR CEDA](https://catalogue.ceda.ac.uk/uuid/470e43e166c44e5990f4f74bc90562d6/)。

```bash
.venv/bin/python download_files.py esgf --model CMCC-CM2-VHR4 --member r1i1p1f1 --table 6hrPlevPt --variables tas uas vas psl --start-year 1950 --end-year 1950 --out downloads/cmcc_manifest.jsonl
.venv/bin/python download_files.py esgf --model ECMWF-IFS-HR --member r1i1p1f1 --table 6hrPlevPt --variables tas --start-year 1950 --end-year 1950 --out downloads/ifs_hr_manifest.jsonl
.venv/bin/python download_files.py fetch --manifest downloads/cmcc_manifest.jsonl --out downloads/cmcc --dry-run
```

先检查成员、时间表、版本、变量和文件大小，再移除 `--dry-run`。这里的成员是可配置示例，不宣称论文恰好用了这个成员。
脚本默认用已验证的 DKRZ 搜索节点，支持 `--endpoint` 更换节点；依据 [ESGF API](https://esgf.github.io/esg-search/ESGF_Search_RESTful_API.html)。
仅下载匹配变量/年份的整文件，并在源提供 checksum 时校验。年份筛选按文件覆盖范围判断，文件内仍可能含多余日期；用 `subset` 再选日期。
气候模拟的 1950 年不是对应历史真实天气的逐时重建，不能按同日期直接作为风电场观测标签。

MERRA-2 使用 [NASA GES DISC](https://disc.gsfc.nasa.gov/)；地表可从 `M2T1NXSLV` 开始，高空气压层查看 `M2I3NPASM`。具体集合、时间平均/瞬时定义和变量需与实验对齐。

1. 注册 Earthdata，并授权 GES DISC。
2. 在集合页使用 **Subset / Get Data**，选择时间、变量、区域，导出子集下载 URL 清单。
3. 把 URL 清单保存为 `merra2_urls.txt`，使用下载器：

```bash
read -rsp 'Earthdata token: ' EARTHDATA_TOKEN; echo
export EARTHDATA_TOKEN
.venv/bin/python download_files.py fetch --manifest merra2_urls.txt --out downloads/merra2 --earthdata
```

NASA 端是否先做子集取决于导出的链接；若导出原文件链接，此脚本将下载整文件。此工具没有自动创建 NASA 子集任务。官方流程及限制见 [NASA MERRA-2 子集说明](https://forum.earthdata.nasa.gov/viewtopic.php?t=5678)。

ISD 仅用于站点评估，可从 [NOAA ISD](https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database)下载站点元数据，按距离选择站点和年份，然后把其 HTTPS 数据链接交给同一个 `fetch` 命令。

## 9. 已有文件提取最近点 / 附近圆形区域

```bash
# 替换输入文件路径；保存 actual lat/lon、distance_km，可额外导出 CSV
.venv/bin/python download_region.py subset --input path/to/data.nc --point --lat 36.3 --lon 120.33 --csv --out downloads/extracted
.venv/bin/python download_region.py subset --input path/to/data.nc --radius-km 50 --out downloads/extracted
```

GRIB 可另装 `cfgrib` 和所需 ecCodes，然后加 `--engine cfgrib`。异构 GRIB 可能需要先按层类型拆分；本工具不自动合并不兼容 GRIB 消息。
子集输出文件名包含输入文件名和选择参数指纹；不同坐标/半径会分开保存。
对于 OPeNDAP URL，`subset --engine netcdf4 --input URL` 可尝试远端切片；认证与节点支持由用户按服务方文档配置，本次未做认证服务验证。

## 10. 用于风电预测时的注意点与验证范围

- 最近网格点适合作为风电模型的气象特征；10 m/100 m 风并不等于风机轮毂高度的实测风。U/V 转风速使用 `sqrt(u**2 + v**2)`。
- ERA5 是事后再分析。在真正的提前预测评估中，要检查气象数据当时是否可获得，避免未来信息进入输入。历史天气预报应同时保留起报时间与预报时效。
- 单点气象数据不能据此直接视为官方预训练 Aurora 的完整输入。官方示例还使用空间网格、多个气压层、静态变量和两个历史时刻；局地区域能否可靠运行需要单独验证/适配。参见 [Aurora 官方 ERA5 示例](https://microsoft.github.io/aurora/example_era5.html)。

已验证：区域/最近点/经度周期/闰日/请求构造与重复运行测试通过；公开 WeatherBench ERA5 单日最近点和周围 50 km 的真实小样本；CMCC、IFS-HR、GEFS 档案清单查询。
真实样本已在开发环境验证；仓库不包含下载数据。新服务器可运行 `bash examples/nearest_point.sh` 生成自己的样本。
CDS、ADS、NASA、MARS 的受认证下载未执行，尚需相应账户、条款接受或档案权限。不会把 dry-run 当作下载成功，也不会声称已复刻论文完整训练语料。

运行测试：

```bash
.venv/bin/python test_download.py
```
