# ikkem 集群参考

**ikkem** = 嘉庚创新实验室智能计算中心（嘉庚智算中心，[AI4EC Lab](https://ai4ec.ac.cn/zh/intro/hpc)），
厦门大学，SLURM 调度。官方手册与联系方式见该页面（ikkemhpc@xmu.edu.cn）。

**文档可能过时，一切以实时探测为准**（`sinfo -s` / `scontrol show ...`）。
下面的快照是 2026-09-03 的实测，仅作探测的起点参考。

## 实测快照（2026-09-03）

- 登录节点主机名 `mu012`，本机 ssh 别名 `ikkem`。别名定义在 `~/.ssh/config`：

  ```
  Host ikkem
    HostName 10.26.14.64
    User gongyulei
    IdentityFile ~/.ssh/ikkem_id_rsa
  ```

  换机器使用时把该配置块写入对应机器的 `~/.ssh/config`（用户名/密钥路径按实际调整），
  或把 target 里的 `host` 直接写成 `gongyulei@10.26.14.64`。
- 官方硬件口径：390 CPU 节点 + 6 GPU 节点（8× A100 80GB SXM，1.5TB 内存）+ 2 胖节点（2TB 内存）。
  注意：GPU 节点的 gres 类型标签实测是 `gpu:tesla:8`，与官方硬件描述（A100）不一致——
  gres 类型只是管理员起的标签，以 `scontrol show node` 实测为准。
- 分区：

  | 分区 | 节点 | 说明 |
  |---|---|---|
  | `cpu`（默认） | cu[001-389] | CPU 作业，0.02 元/核时 |
  | `gpu` | gpu[001-003,005-006] | 整卡，节点 `Gres=gpu:tesla:8`（8 卡/节点），6 元/卡时 |
  | `gpu-mig-2g-20gb` | gpu004 | A100 MIG 切片，节点 `Gres=gpu:nvidia_a100_2g.20gb:24` |
  | `fat` | fat[001-002] | 大内存节点，0.3 元/核时 |

- 计费存在（核时/卡时），别提交空挂作业；登录节点有任务查杀，不能跑计算。
- 分区 `MaxTime=UNLIMITED`，但实际作业被分配了 `TimeLimit=2-00:00:00`（QOS 默认）；
  `sacct` 可用。
- 已验证的坑：`gpu-mig-2g-20gb` 分区**不接受 typed gres**
  （`--gres=gpu:nvidia_a100_2g.20gb:1` 被拒），要用非 typed 的 `--gres=gpu:1`
  （submit.py 的 `--gpus 1` 即生成此写法）。其他分区是否要求 typed gres 以实测为准。

## 已验证的 target 配置

```json
{
  "targets": {
    "ikkem-mig": {
      "backend": "slurm",
      "host": "ikkem",
      "partition": "gpu-mig-2g-20gb",
      "gpus": 1,
      "mem": "8G"
    }
  }
}
```

实测通过的操作链：submit（job 3673521）→ status（pending/running）→ logs → collect。

## wiki 文档（可能过时）

<https://wiki.cheng-group.net/wiki/cluster_usage/gpu_usage/> 记录的是课题组旧集群
（`gpu1`/`gpu2`/`gpu3` 分区、191 节点提交），与当前实况**不一致**，仅其中
SLURM 基础命令（sbatch/squeue/scancel/scontrol）和 LSF 对照表仍有参考价值。
