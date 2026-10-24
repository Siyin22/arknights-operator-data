# 解析工具与依赖

| 目录 / 文件 | 用途 |
| --- | --- |
| `Il2CppDumper-patched/` | 已适配当前客户端的解析器，提取流程实际调用的版本。 |
| `TypeExport/` | 类型信息导出器；`bin/Release/net8.0/` 是运行文件，`Program.cs` 与项目文件是维护源码。 |
| `flatc/` | 官方 FlatBuffers 编译器，用于交叉核验解析结果。 |
| `python/` | 当前解析器使用的本地 Capstone 反汇编库。 |
| `source/Il2CppDumper-6.7.46/` | 上述适配版的源码及原许可证，供后续客户端升级时维护。 |
| `Ark-Unpacker-LICENSE.txt` | LZ4AK 解码参考实现的许可证。 |

`source` 不是另一套旧版可执行工具，须与适配版一起保留。
两个 .NET 项目均引用 `Il2CppDumper-patched/Mono.Cecil.dll`，不再依赖已清理的原版目录。
提取产物统一写入 `work/提取临时/`，不应存放在工具目录。
