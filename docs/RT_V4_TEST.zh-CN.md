# Revelation RT v4 测试包（去"廉价感"第一轮）

目标：Minecraft 1.21.1 Fabric / Iris 1.8.14-beta.1。原作者 HaringPro，Apache-2.0 保持不变。
本轮只做构建与编译校验，**未进行游戏内验收**；帧率与观感需要你在客户端确认。

## 为什么之前看起来"廉价"

对着 v3 的截图逐项回查代码，能定位到四个成因，都不是审美问题而是标定错误：

1. **局部光被硬拉了 8 倍。**
   `lib/lighting/LocalLights.glsl` 里 `incident = RTEmitterColor * (RT_LOCAL_BRIGHTNESS * BLOCKLIGHT_BRIGHTNESS * 8.0 * attenuation)`，
   `attenuation ≈ 1/(1+d²)`。1 格处约等于原版方块光的 4 倍，ACES 也救不回来，于是灯笼周围一大片纯白、纹理被冲掉。

2. **原版方块光被关掉了。**
   `shaders.properties` 的 RT 档位把 `SSILVB_BLENDED_LIGHTMAP` 从原版 `0.15` 改成 `0.0`；
   而开启 `SSILVB_ENABLED` 后 `CombineLighting.frag` 里 `#ifndef SSILVB_ENABLED` 那段方块光/环境光整段不参与编译。
   两者叠加 = 场景里只剩那个过亮的追踪光，超出半径立刻死黑。

3. **遮挡是单条二值射线。**
   `RTSceneOccluded()` 返回 bool，没有半影。灯笼照在墙上的明暗交界就是刀切硬边，
   落在方块盒形几何上还会出现贯穿面片的斜直线。

4. **光图集按 16×16 图块的"中心像素"剔除。**
   `SelectLocalLights.comp` 只读 `tile*16+8` 一个像素的深度；中心落在天空上，整块就一个光源都不选，
   同屏相邻图块亮度跳变。

另外 `RT_HANDHELD_RADIUS` 默认 `0.0`，手持光阴影默认也是最硬的单射线。

## v4 改了什么

| 位置 | 改动 |
| --- | --- |
| `lib/lighting/LocalLights.glsl` | 能量重标定：`2.0` 而不是 `8.0`，15 级光源在 1 格处峰值约等于原版方块光峰值，不再削顶。距离窗 `1-(d/r)^4`，14 格（红石火把 7 格）归零。 |
| 同上 | 软阴影：在光源自身发光面圆盘上取 `RT_LOCAL_SHADOW_SAMPLES` 个黄金角样本，圆盘半径按光源类型 0.10 / 0.20 / 0.30。近处遮挡盖满整盘 → 硬，远处只盖一部分 → 半影，即接触硬化，不需要额外模糊。样本随蓝噪声逐帧旋转，由 TAA 收敛。 |
| 同上 | 新增局部光源 GGX 高光项 `RT_LOCAL_SPECULAR`（默认 0.75）。 |
| `program/prepare/SelectLocalLights.comp` | 改用图块内 5 个采样点的**最近**表面做剔除，中心落天空不再导致整块丢光。 |
| `program/CombineLighting.frag` | 去掉 `!RTLocalCovered(texelPos)` 这个按图块开关方块光的判断（16 像素硬接缝的来源），去掉 main 里重复的 include。 |
| `lib/lighting/PathTracing.glsl`、`program/diffuse/VarianceEstimate.comp` | 同步去掉按图块清零方块光的特判，间接光的反弹基底恢复。 |
| `lib/Setting.glsl` + `shaders.properties` | `SSILVB_BLENDED_LIGHTMAP` 恢复 `0.15`；新增 `RT_LOCAL_SOFT_SHADOWS`、`RT_LOCAL_SHADOW_SAMPLES`、`RT_LOCAL_SPECULAR`；`RT_HANDHELD_RADIUS` 默认 `0.05`。 |
| `lib/lighting/HandheldTracing.glsl` | 手持光按等级归一化（原来 `level × 0.5`，15 级在 1.5 格处约 2.3，同样过曝）；圆盘样本加入逐像素旋转，去掉固定图案的阴影带。 |
| `lang/zh_CN.lang`、`lang/en_US.lang` | 三个新选项的中英文说明。 |

档位：`RT - 5060 日常` = 4 个阴影采样 / 1 路径 / 1 反弹 / 32 格；`RT - Ultra` = 8 采样；`RT - Cinematic` = 16 采样；`Legacy_GI` 关闭 RT 局部光用于对比。

## 怎么测

1. 把 `Revelation-RT-v4-SoftShadows.zip` 放进实例的 `shaderpacks`，在 Iris 里选中它。新文件名不会沿用 v3 的选项文件，默认值即本轮标定值。
2. 先选 `RT - 5060 日常`，站在同样的洞口灯笼场景对照 v3 截图。
3. 建议按顺序看：
   - 灯笼旁边的土块：应当有纹理和渐变，不再是一片纯白。
   - 灯笼在地面上投的影：应当是带半影的软边，而不是刀切。
   - 洞壁外侧（没有被直接照到的面）：应当有很暗但可辨的底光，不是纯黑。
   - 缓慢左右平移视角：不应出现 16 像素见方的亮度方块跳变。
   - 手持火把绕石块/台阶走：阴影边缘不应出现固定图案的灰色带状。
4. 记录日常档室内/室外帧率和 RT_Ultra 对照。

## 可调项（都在"光影设置 → Lighting → Ray Tracing"里）

- `局部光源阴影采样数 RT_LOCAL_SHADOW_SAMPLES`：1 = 硬边（最快），4 = 默认，8/16 = 更平滑的半影。花的是网格射线预算。
- `局部光源软阴影 RT_LOCAL_SOFT_SHADOWS`：关掉回到单条射线，用于排查是不是它带来的开销或噪点。
- `局部光源亮度 RT_LOCAL_BRIGHTNESS`：默认 1.0 已按原版标定；想要更"亮眼"最多到 2.0。
- `局部光源高光强度 RT_LOCAL_SPECULAR`：光滑石面上火把的反光比例。
- `Lightmap 混合 SSILVB_BLENDED_LIGHTMAP`：远距离底光。想更接近原版观感可升到 0.25。

## 边界（未变）

- 仍然是屏幕空间 + 局部体素网格的软件光追，不是硬件 RTX 光追。屏幕外的遮挡物、未提交给阴影阶段的几何、64 格网格以外的方块仍拿不到。
- 没有完整多次反弹的能量守恒、折射、焦散。间接光靠屏幕空间路径 + 历史累积，移动时会有短暂的收敛过程。
- 每屏幕 16×16 图块最多 4 个光源、全场景最多 256 个；光源极密处可能丢掉最弱的贡献。
- 编译校验 176 项（RT_5060 / RT_Ultra / RT_Cinematic / Legacy_GI 四档，44 个入口的编译 + 链接）全部通过，只证明构建有效，不代表观感与帧率达标。报告见随包 `validation/build-v4.json`。
