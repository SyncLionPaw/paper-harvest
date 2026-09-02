---
name: ikkem-slurm
version: "0.1.0"
description: 向 ikkem 集群（SLURM 调度）提交和管理长时间运行的 GPU/CPU 作业。适用于在 ikkem 上跑训练、DP-GEN、VASP、CP2K 等长任务，查看或取消已提交的作业，以及回收已完成作业的结果和日志。
---

# ikkem SLURM 交作业

**ikkem** = 嘉庚创新实验室智能计算中心（嘉庚智算中心 / IKKEM Intelligent Computing Center，
[AI4EC Lab](https://ai4ec.ac.cn/zh/intro/hpc)），厦门大学。SLURM 调度，
登录节点 `mu012`，本机通过 ssh 别名 `ikkem` 访问。作业按核时/卡时计费。

所有操作只通过 `scripts/submit.py` 完成，不要手写 sbatch 脚本。
集群文档可能过时，**每次提交前必须实时探测**，以探测结果为准。

## 1. 实时探测（每次必做）

先确认 ssh 别名可用：

```bash
ssh -o BatchMode=yes -o ConnectTimeout=5 ikkem true   # 失败 = 本机未配置别名
```

失败时按 [references/cluster.md](references/cluster.md) 里的配置块帮用户配置
`~/.ssh/config`（用户名/密钥需向用户确认），再继续。

然后探测集群实况：

```bash
ssh ikkem 'sinfo -s'                              # 分区列表与节点空闲
ssh ikkem 'squeue'                                # 排队情况
ssh ikkem 'scontrol show partition <分区>'         # 时限、默认内存等
ssh ikkem 'scontrol show node <节点> | grep Gres'  # 该节点的 gres 写法
```

- 分区名、gres 写法、资源限制会变，**不要照抄任何静态文档**（包括本 skill 的快照）。
- 若 `sbatch` 拒绝，错误信息会直接说明正确写法（例如 typed gres 被拒时改用 `--gres=gpu:1`）。
- 历史实测快照见 [references/cluster.md](references/cluster.md)，仅作参考起点。

## 2. 提交与管理

target 配置在项目 `submit-job.json` 或 `~/.config/submit-job/config.json`，按探测结果填写：

```json
{"targets": {"ikkem": {"backend": "slurm", "host": "ikkem", "partition": "<分区>", "gpus": 1}}}
```

```bash
python3 scripts/submit.py submit --target ikkem --name <作业名> --cmd '<命令>' [--dry-run]
python3 scripts/submit.py status  --job <作业名>     # JSON: pending/running/completed/failed
python3 scripts/submit.py logs    --job <作业名>     # 原始日志
python3 scripts/submit.py cancel  --job <作业名>
python3 scripts/submit.py collect --job <作业名>     # rsync 回收整个远程工作目录
```

- `--cmd` 里可以直接用 `module add <env> && <命令>` 加载环境。
- 先 `--dry-run` 检查生成的 sbatch 脚本再真正提交。
- 作业名即句柄，状态存于 `.submit-job/<作业名>.json`。

## 规则

- 提交后把 `job_id`、`workdir`、`log` 报告给用户。
- 监控用 `status` 分钟级轮询，不空转。
- `collect` 前确认 `state` 为 `completed` 且 `exit_code` 为 0；失败先用 `logs` 定位原因。
- 结果在本地验证通过之前，不清理远程目录。
- **计费**：CPU 按核时、GPU 按卡时收费，提交前与用户确认资源量，避免空挂作业。
- **登录节点禁止跑计算**（官方会查杀）：只在上面提交/查询/传文件，计算一律走 SLURM。
