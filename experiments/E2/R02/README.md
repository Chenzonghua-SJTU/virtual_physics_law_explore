# E2 R02：实验归档

本目录保存接口简化后的15次真实探索结果、配置、哈希、范围调整和审计脚本。

- [完整实验报告](../R02.md)
- [E2轮次索引](../README.md)
- [实验总记录](../../experiment.md)
- [案例分析](case_notes.md)

原experiments/E3目录已整体迁入本目录，旧目录已删除。原始JSON中的历史路径、会话编号E3-*、镜像名和Git提交保留，作为原始记录而非新的实验编号；其中旧归档路径应按此次目录迁移映射读取。

在项目根目录运行本目录analyze.py、interface_audit.py和report.py可复核本地记录，报告生成到experiments/E2/R02.md。复核不调用模型，原始本地runs档案不随仓库上传。continue_code_only.py仅保存当时接管在途会话的控制器，不用于启动新实验。
