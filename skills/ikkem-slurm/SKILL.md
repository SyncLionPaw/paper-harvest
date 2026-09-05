---
name: ikkem-slurm
version: "0.1.4"
description: 向 ikkem 集群（SLURM 调度，嘉庚/厦大内网）提交和管理长时间运行的 GPU/CPU 作业。适用于在 ikkem 上跑训练、DP-GEN、VASP、CP2K 等长任务，查看或取消已提交的作业，以及回收已完成作业的结果和日志。
---

# ikkem SLURM 交作业

**ikkem** = 嘉庚创新实验室智能计算中心（嘉庚智算中心 / IKKEM Intelligent Computing Center，
[AI4EC Lab](https://ai4ec.ac.cn/zh/intro/hpc)），厦门大学。SLURM 调度，
登录节点 `mu012`（内网 `10.26.14.64`）。集群只在嘉庚/厦大内网可达，公网连不上；
ssh 超时或无路由 = 本机不在内网，先让用户确认网络，不要改脚本、不要找公网入口。
本机 ssh 别名**不一定叫 `ikkem`**，也可能根本没配——先解析再连，不要默认
`ssh ikkem`。作业按核时/卡时计费。

## 铁律（先读这个）

1. **只通过 `scripts/submit.py` 操作集群**。禁止自己写 sbatch 脚本、禁止直接
   `ssh <host> '<命令>'` 在集群上执行任何操作（传文件、查目录、跑命令都不行）。
   submit.py 不支持的需求，先告诉用户，不要绕过。
2. **不碰无关目录**。只访问：用户指定的本地项目目录（`--src` 的内容）、
   远程作业工作目录（`~/submit-jobs/<作业名>/`，由 submit.py 管理）。
   不要在本地或远程翻找、遍历其他目录；需要的信息向用户要。
3. **提交前必须实时探测**（见下），集群文档可能过时，以探测结果为准。

## 1. 解析 ssh 目标（每次提交前必做）

别名不一定叫 `ikkem`，也可能没配。先解析 `host`，再探测：

1. 读 `~/.ssh/config`，找 `HostName 10.26.14.64`（或用户告知的登录节点）对应的
   `Host` 别名；只看这一条，不要翻其他 Host。
2. 也看项目 `submit-job.json` / `~/.config/submit-job/config.json` 里已有 target
   的 `host`。
3. **找到了**：后面一律用这个 host（`probe --host <别名>`，target 的 `host` 写成它）。
4. **没找到**：向用户要用户名和密钥路径，按 [references/cluster.md](references/cluster.md)
   写一块（`Host` 名让用户定，或直接用 `user@10.26.14.64`），写完再做连通性检查。
   不要擅自假定别名叫 `ikkem`。

连通性：

```bash
ssh -o BatchMode=yes -o ConnectTimeout=5 <host> true
# 超时 / No route to host = 不在内网，停
# Could not resolve / Permission denied = 别名或密钥不对，问用户
```

然后用 submit.py 的探测模式看集群实况（等价于 sinfo/squeue/scontrol，只读）：

```bash
python3 scripts/submit.py probe --host <host>                       # 分区列表 + 排队情况
python3 scripts/submit.py probe --host <host> --partition <分区>     # 时限、默认内存、节点 gres
```

- 分区名、gres 写法、资源限制会变，**不要照抄任何静态文档**（包括本 skill 的快照）。
- 若提交被 sbatch 拒绝，错误信息会直接说明正确写法（例如 typed gres 被拒时改用 `--gpus`，
  即生成 `--gres=gpu:1`）。
- 历史实测快照见 [references/cluster.md](references/cluster.md)，仅作参考起点。

## 2. 提交与管理

target 配置在项目 `submit-job.json` 或 `~/.config/submit-job/config.json`，按探测结果填写：

```json
{"targets": {"ikkem": {"backend": "slurm", "host": "<上一步解析到的 ssh 目标>", "partition": "<分区>", "gpus": 1}}}
```

**所有命令都在用户指定的项目目录下运行**（作业状态存在该目录的 `.submit-job/`，
status/logs/cancel/collect 必须和 submit 在同一个目录下执行）：

```bash
python3 scripts/submit.py submit --target ikkem --name <作业名> --cmd '<命令>' \
    [--src <本地目录>] [--exclude <模式>] [--dry-run]
python3 scripts/submit.py list                        # 列出本地跟踪的作业
python3 scripts/submit.py status  --job <作业名>       # JSON: pending/running/completed/failed/cancelled
python3 scripts/submit.py logs    --job <作业名>       # stdout + stderr 尾部
python3 scripts/submit.py cancel  --job <作业名>
python3 scripts/submit.py collect --job <作业名>       # rsync 回收整个远程工作目录
```

- **代码/数据上传**：`--src <本地目录>` 在提交前把该目录 rsync 到远程工作目录
  （`~/submit-jobs/<作业名>/`），`--cmd` 里的相对路径即相对于该目录。
  训练任务典型用法：`--src ./train_project --cmd 'module add <env> && python train.py'`。
  `.venv`、`__pycache__`、大数据文件不要上传：用 `--exclude .venv --exclude '__pycache__'`
  排除（可重复），其余先让用户精简再提交。
- `--cmd` 里可以直接用 `module add <env> && <命令>` 加载环境。
- 先 `--dry-run` 检查生成的 sbatch 脚本和同步计划，再真正提交。
- 作业名即句柄，状态存于 `.submit-job/<作业名>.json`。

## 规则

- 提交后把 `job_id`、`workdir`、`log` 报告给用户。
- 监控用 `status` 分钟级轮询，不空转。
- `collect` 前确认 `state` 为 `completed` 且 `exit_code` 为 0；失败先用 `logs` 定位原因
  （stderr 在 `.err` 文件，`logs` 会一并显示）。
- 结果在本地验证通过之前，不清理远程目录。
- **时限**：ikkem 的 QOS 默认 wall limit 为 2 天。预计更久的任务要用 `--time` 显式申请
  （上限以 probe 实测为准），并在 `--cmd` 里做好 checkpoint/续跑；超时被杀后改名重新提交续跑。
- **计费**：CPU 按核时、GPU 按卡时收费，提交前与用户确认资源量，避免空挂作业。
- **登录节点禁止跑计算**（官方会查杀）：计算一律走 SLURM 作业，这也包括任何
  "先 ssh 上去跑个小命令看看" 的行为——探测用 `probe`，其余都在作业里做。
