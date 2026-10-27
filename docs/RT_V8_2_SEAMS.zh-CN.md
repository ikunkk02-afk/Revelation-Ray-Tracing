# Revelation RT v8.2：多灯接缝回归与启动链接时间

目标：Minecraft 1.21.1 Fabric / Iris 1.8.14-beta.1。2026-10-27。

## 用户报告的问题

同一房间里多盏吸顶灯的交界处，墙面与地面出现**链状 / 16 px 阶梯状的阴影**。
截图（`2026-10-27_02.19.36.png`）取自 **v7.1 + Default 档**，不是 v8。

## 接缝的成因

v7.1 的选择器（`SelectLocalLights.comp`）对每个 **16×16 像素图块**只保留距离最近的
**4 盏灯**，接收位置由 5 个深度采样决定。密集灯阵里相邻图块会突然换成另一组灯，
同一面连续墙上被丢弃的那盏灯形成一块块 16 px 的硬边——就是截图里的链状阴影。
体积散射当时只用第一盏灯，同样会切换。

v8 已把它改成两个 128 位掩码（最多 256 盏灯）+ 图块侧面保守视锥测试 + 逐像素按
距离/朝向/有限半径剔除。v8.2 把这件事固化成可复现的 GPU 回归，并用 v7.1 的旧选择器
作为**必须失败**的对照。

## 回归结果（`validation/seam-v8.json`，RTX 5060 Laptop）

| 场景 | 掩码 vs 穷举最大误差 | 当前 16 px 边界台阶 | v7.1 对照台阶 |
| --- | --- | --- | --- |
| 12 灯一字排开（吸顶灯） | 0.0 | 0.0 | 0.0391 |
| 12 灯交错两排 | 0.0 | 2.8e-05 | 0.2037 |
| 10 灯随机 | 0.0 | 1.0e-05 | 0.0457 |

- “掩码 vs 穷举”逐像素比较：当前实现与一次性遍历全部灯的结果**完全一致**（误差 0.0）。
- “16 px 边界台阶”：把跨越 x=16k 的跳变与它两侧同行跳变比较，只有落在图块网格上的
  不连续才会产生正值。当前实现≈0，v7.1 对照是它的 3 700～7 000 倍。
- 逐灯穷举还验证了每个图块的掩码是**“所有对该图块像素有贡献的灯”的超集**：
  12/12、12/12、10/10，无遗漏。
- 局部体积散射在图块边界连续（台阶 7.5e-05）。

`validation/seam-v8.png` 为同灯同接收面的三图对照：v7.1 / 当前 / 6 倍放大的差值。

`scripts/seam_checks.py` 是可重复运行的入口：

```
PYTHONPATH=<glfw+PyOpenGL 目录> python scripts/seam_checks.py
```

## 启动卡在 “Creating pipeline for dimension”

对挂起的进程做 jstack，渲染线程停在：

```
GL20C.glLinkProgram
  net.irisshaders.iris.gl.shader.ProgramCreator.create
  net.irisshaders.iris.gl.program.ProgramBuilder.beginCompute
  net.irisshaders.iris.pipeline.CompositeRenderer.createComputes
```

即 NVIDIA 驱动在**链接计算程序**，不是 Java 崩溃、不是 TDR、不是显存不足。
把每个入口点单独测时（`scripts/link_timing.py`，`validation/link-times-v8.2.json`）：

| 程序 | 内容 | v8 | v8.2 |
| --- | --- | --- | --- |
| `world0/composite2.csh` | 半透明面光照（水/玻璃） | 98.9 s | 12.8 s |
| `world0/deferred20.csh` | 半分辨率局部漫反射缓存 | >60 s 未完成 | 8.0 s |
| `world0/deferred50.fsh` | `CombineLighting.frag` 原生分辨率表面光照 | 19.8 s | 3.1 s |

其余 54 个计算入口与其余片元程序都在 1 s 内，没有其他异常点。

两处改动（语义不变，全是编译期问题）：

1. 面积光追踪器里的位扫描 `while (bits != 0u)`（配合 `findLSB` 逐位弹出）改成
   **上界来自 uniform 的 `for` 循环 + 位测试**。语义相同：仍然遍历全部被掩码选中的灯、
   仍按索引递增顺序累加，插入顺序无关性与能量守恒测试全部保持通过；只是不再让驱动把
   整个追踪器按掩码字复制多份。
2. `lib/lighting/LocalLights.glsl` 顶部加 `#pragma optionNV(unroll none)`。这些循环本来
   就是运行期上界，展开只会烧编译时间。未知 pragma 在非 NVIDIA 驱动上按 GLSL 规范忽略。

残留的约 9 s 集中在 `composite2` 的**染色玻璃光路**：关掉 `RT_GLASS_ENABLED` 后同一程序
3.3 s；而把 16 项染料表替换成常量对耗时没有影响（12.66 s），说明成本在 pane 几何排序，
不在颜色表。想要更快的首帧链接，可以先关染色玻璃。

## 首次加载的档位

`Setting.glsl` 的默认值仍等于最高画质（RayTracing）。压缩包里同时给出
`Revelation-RT-v8.2-SeamStartupFix.zip.txt`，把首帧链接压到秒级（`Default` 量级的
采样数、2048 阴影、半分辨率局部漫反射）。想用最高档：进游戏后在光影设置里选
「光线追踪」，那一次切换需要等链接完成。
