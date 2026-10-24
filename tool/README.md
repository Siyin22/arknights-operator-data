# 明日方舟 · 干员版本对比工具

日常双击 `启动工具.vbs`，点击“提取并上传 GitHub”。使用说明见 `使用说明.txt`。

工具与数据仓库：https://github.com/Siyin22/arknights-update-tool （公开）。首次安装见 `安装说明.txt`。

## 当前流程

1. 校验已适配的本机国服 PC 客户端程序与元数据指纹。
2. 读取当前资源清单，仅提取 character、char_patch、skill、uniequip、battle_equip、building_data 六张表及 data_version.txt。
3. 从当前客户端静态恢复类型和原生读取字段，自行生成 FBS；不下载第三方数据快照。
4. 解析六张表，并用官方 flatc 与独立 Python 读取器交叉核验。
5. 生成满级满信赖干员数据、技能七级/专精、后勤技能与模组各级效果，按官方 VersionControl 保存 Git 提交和同名标签。
6. 生成新增、修改、移除报告；成功后清理固定临时目录，再上传 GitHub。

国服 Windows x64 客户端 2.7.81 / 官方数据版本 78.2.0 已验证。程序指纹变化时停止适配，不能只修改指纹绕过检查。
提取过程离线，只读游戏文件；GitHub 上传使用 gh 的现有登录。没有进程注入或执行 GameAssembly。

## 固定目录与模块

- GitHub 仓库根目录保存干员、模组 JSON、版本信息、更新报告与 Git 历史，`tool/` 保存完整工具；从 `tool/` 启动时直接维护上一级仓库。原本地布局仍使用工具目录下的 `版本数据/` 独立 Git 仓库。
- `work/提取临时/`：固定临时工作目录。成功后删除；失败时保留诊断供排查，下一次运行重建。
- `work/版本对比/`：手动选择两个版本的比较结果，覆盖固定文件。
- `src/archive_store.py`：生成确定性快照、Git 提交和官方版本标签；同版本同内容不重复提交；不同内容同版本拒绝覆写。
- `src/version_compare.py`：独立标准库对比器，复制为数据仓库 compare.py；用 git archive 读取任意两个标签，不 checkout 或改动工作树。
- `src/github_sync.py`：固定仓库同步；仅子进程设置代理，连接/总请求有超时，只读网络失败可从代理回退直连。上传不自动重试不确定写入，不强推。
- `src/operator_details.py`：最高精英阶段/等级、满信赖、潜能加成、天赋选择、描述参数解析、职业形态与模组关联、后勤技能与设施及解锁条件。
- `src/pipeline.py`：固定临时目录、全局进程锁、取消与超时、成功后清理。CLI 只本地保存，GUI 默认再上传。
- `src/app.py`：提取上传、单独重试上传、两个数据版本选择、查看报告与图片导出。
- `src/report_renderer.py` + `src/report_assets/`：统一离线页面，双版本标识、PRTS 风格的资料表格、html2canvas 单项 PNG 与 UTF-8 ZIP 批量导出；更新报告和任意版本比较共用。
- `version-info.json`：历史客户端版本的核实补充信息；旧标签不可改写，读取标签时允许补全客户端元信息。`verified_current` 校验 HEAD 包含对应标签且干员、模组及补全后的版本数据一致，允许后续报告样式提交。
- `src/export_excel.py` / `src/export_updates.py`：保留的兼容源码与回归测试对象，前者的职业、技能类型映射仍由当前解析器使用；不是日常入口。

Git 历史保存版本差异，不保留每次运行的整套副本。标签不可静默改写；遇到同号热修需核对后单独适配版本策略。

## 工作区保留内容

- `.venv/`：当前 Python 运行环境。
- `adapters/`：已核实客户端的适配指纹。
- `src/`：工具界面、提取解析、版本保存、报告与图片导出源码。
- `tests/`：解析与版本对比的回归检查。
- `tools/`：实际使用的解析器、编译器、反汇编库及适配源码，细目见 `tools/README.md`。
- `work/`：可再生成的临时工作目录；本地保留最新活动的 5 张示例与必要验证脚本，不上传临时输出。
- `requirements*.txt`：Python 依赖及版本清单。
- `pipeline.lock`：运行时自动生成的并发锁文件。

旧安装压缩包、未适配的原版 Il2CppDumper、早期解析产物、浏览器测试缓存、预览图片与重复报告已移入回收站。

## 维护与验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe src\pipeline.py 'D:\Hypergryph Launcher\games\Arknights Game'
.\.venv\Scripts\python.exe src\version_compare.py <旧版本> <新版本> --repo 版本数据 --output work/版本对比
```

在 GitHub 版的 `tool/` 目录运行最后一条命令时，将 `--repo 版本数据` 改为 `--repo ..`。

版本从 `data_version.txt` 的 `VersionControl` 读取，资源版本也保存在 version.json，但不作为目录名。
Git 提交者只在本地数据仓库设置，使用 GitHub noreply 邮箱，不改全局 Git 配置。
上传允许已提交的数据、报告与 `tool/` 源码及运行依赖，推送 main 与官方标签；本机环境、设置和临时产物不上传。新增数据版本只暂存生成的数据与报告文件，不会自动提交工具源码修改。

历史 78.2.0 的后勤技能由同一资源版本重新提取补齐；先核对全部已有战斗数据完全一致，再保存 `base-skills-history.json`，读取旧标签时合并。原标签不改写，资料补齐不算游戏更新；后续后勤技能变动正常参与版本对比。

## 数据口径

- 干员包含可获取的 char_ 以及 patchChars 的职业形态。模组使用 tmplId 优先确定归属，排除默认职业证章。
- 属性采用最高精英阶段的最高等级关键帧，加满信赖与所选潜能；不叠加模组或实战天赋、技能增益。
- 关联召唤物记录最高阶段最高等级基础值，不推导融合、实战继承或动态机制。
- 模组每一级显示该级总加成，不累加各级；特性、天赋按解锁条件与潜能筛选，保留限定模式。
- 技能描述替换 blackboard 参数、百分比与换行；未提供的参数明确标记，不猜值。
- 后勤技能按满级条件显示各组最终效果，注明设施、解锁条件及替换的旧技能；JSON 保留各解锁阶段。职业切换形态依据官方映射共享原干员的后勤技能，异格干员独立读取。
- 任意两版本比较已保存的可读数据，不包含剧情、基建、装备材料等本工具没有导出的配置变化。
- 首次导出只建立基准。数值修改、移除和新增分别展示；同一版本重复提取不制造假变化。

## 解析器与适配注意事项

UnityPy 1.25.4 + 本地 LZ4AK 解码，压缩标记 4 不能当作标准 LZHAM；token 半字节交换、距离大端，带边界检查。
Il2CppDumper 6.7.46 本地适配 metadata v29 的 92 字节 TypeDefinition（interfaceOffsetsStart 后有额外字段），禁止 PE 动态加载和交互提示。
TypeExport 使用 Mono.Cecil 提取类型、枚举、字段偏移与 JsonProperty/JsonIgnore。schema/audit 用 Capstone 分析 Unpack vtable；保留 native_verified 与未完全覆盖的特例区别。基建房间泛型父类字段的偏移可能为占位 0；只有槽位完整且已恢复字段全部吻合时保留声明顺序，并标记 native_partial，随后再做 flatc 交叉验证。
生成 FBS 处理泛型、字典、继承遮蔽、Obscured 标量与二维 short 数组。原生读取证据用于排除未序列化字段（如 TileData.advancedBuildableMask / ActionData.useExtraRoute）。
原始 TextAsset 去掉 128 字节签名头读取；没有实现签名真实性验证。未知非零字段、越界、重复键等会失败。
flatc 一致性证明两个读取器一致，不证明所有游戏运行时语义。新增客户端必须重新静态分析结构、核对适配、完整测试后更新 adapters/supported.json。

## 依赖

Python 依赖见 requirements.txt / requirements-lock.txt。Il2CppDumper（MIT）、Mono.Cecil（MIT）、FlatBuffers flatc（Apache-2.0）及 LZ4AK 参考 Ark-Unpacker（BSD-3-Clause）的原始许可证保留在 tools。
正常提取不使用 OpenArknightsFBS 或社区快照。需要联网安装依赖时遵循单次子进程代理偏好，不改变系统或会话代理。

## 图片与版本展示（2.2）

明确区分客户端程序版本与 VersionControl 数据版本。新提取从当前适配器记录客户端版本；已发布 78.2.0 的 2.7.81 元数据来自经指纹验证的适配器，以后续普通提交补充，不改写标签。
报告用 html2canvas 1.4.1（MIT）在本机生成 PNG，依赖与许可证随页面及 report_assets 保存，无 CDN 运行时依赖。批量 ZIP 使用 store 模式和 CRC32，PNG 本身已压缩；一项一张，UTF-8 文件名。HTML 主文件内嵌完整当前资料用于按需导出，但不把全量记录显示为本次新增。

工具界面、离线报告与导出图片优先使用本机安装的“霞鹜文楷”（LXGW WenKai），缺少时使用“微软雅黑”。不附带字体文件，也不在运行时下载字体。

更新报告按干员 ID 归组，各项新增、修改、移除分别标记，对照干员不算版本更新。移除模组使用旧版本所属干员作无模组基准，不混用当前版本。
报告默认使用潜能 1。干员卡片支持勾选所属模组一起展示、合并导出，也支持仅导出干员；模组单图自带同版本、同潜能的全部无模组特性与天赋。清单固定加入时勾选的模组，导出时应用顶部潜能和技能选项。
模组各级保留完整描述。只在名称与生效条件均可唯一对应的相邻等级效果之间比较文字，以淡红色覆盖文字下半部，标记新增或改写内容，片段首尾分隔标点不标记；不按泛称“天赋”推断其替换哪个基础天赋，不把追加描述拼成推测的最终效果。原始快照与官方标签不因展示改进改变。

本次新增干员默认勾选本次新增的所属模组；“导出本次资料”将它们合并成图，不重复导出已合并模组。老干员的新模组单独成图；取消勾选的模组恢复单独导出。
