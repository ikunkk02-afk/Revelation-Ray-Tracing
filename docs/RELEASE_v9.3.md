# Revelation RT v9.3 — 光源调色与手电筒 / Light Controls

2026-10-27。基于 HaringPro/Revelation 的独立维护分支，沿用 Apache-2.0，保留原作者与第三方许可声明。

## 下载与安装

下载本页 Assets 中的 **Revelation-RT-v9.3-LightControls.zip**，无需解压，放进 Minecraft 实例的 `shaderpacks`，在 Iris 中启用。自动生成的 Source code 为开发源码。

目标环境：Minecraft **1.21.1 Fabric**、Iris **1.8.14-beta.1**、支持 **OpenGL 4.6** 的显卡和驱动。离线 GPU 验证使用 RTX 5060 Laptop。不支持 OptiFine。

## 本次内容

- 默认使用稳定单中心阴影，修正随机颗粒和面积光多重孔洞投影问题；保留镂空遮挡与染色玻璃透光。
- 光影设置 → **光源与手电筒**，独立调整方块和手持光源的亮度与 RGB 颜色。自定义颜色默认关闭。
- 普通、灵魂、红石火把可切换为跟随视角的手电筒，主副手均支持；可调张角、柔边和距离，默认关闭。
- 手电筒模式不影响灯笼等其他手持光源；切换画质不会重置调光设置。
- 包含多光源照明、保边半分辨率局部光计算、材质修正，以及六档画质。默认极高，光线追踪为最高负载档。

白色手电筒：开启手电筒和自定义手持颜色，RGB 都设为 1，手持亮度从 1 开始调整。

## 验证与已知限制

656 项编译/链接、414 项行为检查（622,592 条射线）、21 项光源控制和 10 项单投影检查通过，另含接缝、密集光源与 Iris 元数据检查。随包 SHA256SUMS 和构建清单用于核对下载内容，原始验证报告保留在标签源码中。

离线检查不代表 Minecraft 帧率或全部场景画面验收；游戏测试由用户进行。间接光依赖屏幕信息，局部光照有网格范围限制；默认阴影为点光源近似。手电筒照亮表面，不新增空气中的可见光柱。扩展模组、其他硬件和其他 Iris 版本尚需测试。

## English

Download **Revelation-RT-v9.3-LightControls.zip**, place it in your instance's `shaderpacks` folder without extracting, and select it in Iris. Target: Minecraft 1.21.1 Fabric, Iris 1.8.14-beta.1, OpenGL 4.6. OptiFine is unsupported.

This fork adds stable single-center local/held shadows, cutout and colored-glass transmission, independent block/held brightness and RGB controls, and optional view-directed flashlight mode for regular/soul/redstone torches. Beam width, softness and range are configurable. Custom colors and flashlight mode are off by default; quality changes preserve these controls. The flashlight illuminates surfaces without adding a visible volumetric air beam.

656 compile/link, 414 behavior (622,592 rays), 21 light-control and 10 projection checks passed, alongside seam/dense-light and installed-Iris metadata checks. Offline validation does not establish Minecraft FPS, every scene's visual quality or optional-mod compatibility. Original Apache-2.0 licensing, upstream attribution and third-party notices are retained. This is a fork release, not an official upstream release.
