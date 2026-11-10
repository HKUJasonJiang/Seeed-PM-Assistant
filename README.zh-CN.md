# Seeed Studio · L1轻定制小助手

[English](README.md)

这个本地 Windows 工作台供 Seeed 项目经理查询**海外商城**。拿到客户需求后，可以按 SKU 或用途找产品，核对随箱物料、另购配件和地区型号，再把可定制的产品归入同一个需求。随附目录可以直接查询，无需 AI 密钥。

**发给同事，只想先看商品？** 请发完整 ZIP 的下载链接。收件人在自己的 Windows 电脑上下载，右键选「全部解压」，打开解压后与 `data` 文件夹同层的 **`index.html`**。无需安装 Python，首页会显示 J4012，也可搜索 `100025879` 查看 R1014-10。GitHub 中带 `/blob/` 的网址显示源码；`127.0.0.1` 指向收件人自己的电脑，完整工作台需要在那台电脑上启动。[下载完整 ZIP](https://github.com/HKUJasonJiang/Seeed-PM-Assistant/archive/refs/heads/main.zip)

**找不到收藏夹？** 浏览器地址是 `file:///…/index.html` 时，打开的是只读目录预览。请将下载包「全部解压」，回到含有 `index.html` 的文件夹，双击 **`启动助手.cmd`**（或 `Start Assistant.cmd`），使用启动器打开的浏览器页面。新电脑请先按下面的步骤安装。完整工作台左侧有「我的收藏」「定制服务」，左下有「开发者」，右下有 AI 聊天按钮。如果服务已在默认端口运行，可以直接打开收藏页。[在本机打开我的收藏](http://127.0.0.1:8765/#favorites)

## 第一次在 Windows 上安装

1. **检查电脑和 Python。** 使用 Windows 10 或 11 的 x64 电脑和浏览器。打开「开始」，搜索 `cmd`，点「命令提示符」，输入 `py -3 --version` 或 `python --version`。如果已有 **64 位 CPython 3.12 或 3.13**，可直接跳到第 2 步。否则请 IT 安装。个人管理的电脑可在 Python 官网下载 3.13.x 的 **Windows installer (64-bit)**。在传统安装器的第一个界面勾选 **Add python.exe to PATH**，再点 **Install Now**。安装后新开一个命令提示符，重复上面的版本检查。若只打开微软应用商店，请联系 IT。[Windows 版 Python 下载](https://www.python.org/downloads/windows/) · [Python 官方安装说明](https://docs.python.org/3.13/using/windows.html)
2. **下载工作台 ZIP（约 100 MB）。** 可以直接点下面的下载链接，也可以进入项目仓库，在文件列表上方点 **Code → Download ZIP**。等待下载完成。如果公司网络无法访问 GitHub，请 IT 通过公司允许的方式提供压缩包。使用 ZIP 安装无需 Git、Node.js 或 Codex。[直接下载最新版 ZIP](https://github.com/HKUJasonJiang/Seeed-PM-Assistant/archive/refs/heads/main.zip) · [项目仓库](https://github.com/HKUJasonJiang/Seeed-PM-Assistant) · [GitHub 下载帮助](https://docs.github.com/en/repositories/working-with-files/using-files/downloading-source-code-archives)
3. **完整解压。** 在文件资源管理器的地址栏输入 `%USERPROFILE%`，回车，在当前 Windows 用户的目录下新建 `SeeedTools` 文件夹。也可选用你能写入、没有云盘同步的本地文件夹。回到下载位置，右键 ZIP，选择 **全部提取…**，浏览并选中刚才的文件夹。提取完成后，打开能同时看到 `Start Assistant.cmd`、`index.html` 和 `data` 的那层目录，保留整套文件。[微软解压说明](https://support.microsoft.com/en-us/windows/experience/storage-filemanagement/zip-and-unzip-files)
4. **双击 `Start Assistant.cmd`。** 中文入口 `启动助手.cmd` 有相同效果。首次启动会在本安装目录内创建专用运行环境 `.venv`，安装本版指定的 Pillow 12.3.0 和 lxml 6.1.3。请使用公司允许的网络，等待首次下载完成。以后在同一目录启动会复用已安装的版本。请收藏浏览器实际打开的地址，默认是 `http://127.0.0.1:8765/`。如果默认端口已被占用，启动器可选择空闲的本机端口。这个地址只供本机访问。[打开默认地址](http://127.0.0.1:8765/)

**用一分钟验证。** 搜索 `100025879`，首张卡应该是 **reComputer R1014-10**，显示 **2 GB RAM、16 GB eMMC**。点「箱内清单」，找到 **5 只 120 Ω 终端电阻**，旁边的来源能打开官方手册。初次安装完成后，断网也能在本地查询目录。打开官网依据、检查商城更新和发送 AI 消息需要网络。[默认端口的示例商品](http://127.0.0.1:8765/#product=100025879&tab=parts)

平时用完可关闭浏览器标签页。需要停止服务时，双击本安装目录内的 `Stop Assistant.cmd`。它会核对服务所属的安装目录。若提示正在处理目录更新或 AI 请求，请等任务完成后再次双击。直接打开 `index.html` 可以只读浏览目录。需要收藏、编辑、更新和对话时请用启动器。

## 拿到客户需求后怎么用

| 想完成的事 | 在工作台里的操作 |
| --- | --- |
| 找到客户指定产品，提出备选 | 在「选型查询」输入 SKU、型号或需求，例如 `J4012 需要 Super 模式`。指定产品排在首屏。只给系列名称时可能展示一个代表配置。核对具体 SKU，再读备选型号的推荐理由。搜索框下方可展开查询规则。 |
| 准备报价 | 点主卡顶部的完整商品 URL。查看价格或价格区间、币种及商城快照日期。向客户报价前，再通过相应销售渠道确认现价、库存、阶梯价和定制费用。价格留空表示本地没有可用报价数字。 |
| 确认标配和可扩展项 | 用「箱内清单」核对标配，在「配件与定制」按名称、接口、频段或 SKU 同时筛选选配、另购和定制说明。可输入 `wifi` 或 `Wi-Fi`，也可输入「电源适配器」或 `power adapter`。例如搜索 `R1100，客户需要 EU868` 可对照 SPI 模块 `114993268` 与 USB 模块 `114992628`。商品页同时推荐加购默认收起。展开后可核对来源与适用条件。 |
| 返回刚看的页面 | 顶部「上一页」「下一页」各支持五步。可在商品、目录或定制页面间回看，恢复当时的搜索、筛选和页签。 |
| 收藏与管理定制需求 | 在产品卡上点星标收藏。侧栏快捷收藏默认收起，点小三角可展开。「定制服务」支持把一个或多个符合条件的 SKU 放进同一项目，填写标题、需求描述和标签。产品须有适用的厂方定制依据或项目经理的人工确认。 |
| 纠正资料或切换语言 | 在「开发者 → 产品编辑」新增 SKU、修改产品信息或替换主图。本地修改会在目录同步后继续优先显示。在「开发者 → 语言与 AI」切换中英文。商品名、来源原文和自己录入的内容保留原语言。 |

### 随附目录覆盖到哪里

**2026 年 11 月 9 日**核对了三个官网入口。海外商城公开搜索返回 **4,499 个 SKU**，其中 **1,776 个**出现在 15 个 Products 菜单品类中。站点地图与官网商品路由另返回 **22 个 SKU**，逐一访问其普通商城页均返回 HTTP 404。工作台保留这些地图记录以便查手册，报价前需另行核实价格和供货。合并后可搜索 **4,521 个不同 SKU**。

打开「采集概况」可查看核对日期、官网来源、商品页和文档的已查、有内容、空白、失败及排除数量。商品目录正文与商品页的十个独立栏目分别统计。该页也列出历次核对后本地可查的字段、主图和地图对账明细。[打开本地采集概况](http://127.0.0.1:8765/#coverage) · [官网站点地图](https://www.seeedstudio.com/sitemap.xml)

**2026 年 11 月 9 日**逐一访问了 **4,479** 个允许检查的商品页入口，**4,436** 个能核实 SKU 及全部十个栏目。其中 4,370 个至少一栏有内容，66 个十栏均空。另外 43 个入口中，27 个返回 HTTP 404、11 个显示其他 SKU、1 个跳回首页、4 个跳出允许范围。另有 42 个受站点规则或回退地址限制。本地主图覆盖 4,467 个 SKU，共 3,888 张不重复的 JPG。商品页无法打开时，仍可查看公开目录已提供的名称、标价和其他字段。

54 个没有本地主图的产品中，34 个缺少可用的官方图源，20 个有官网图源但未能核实图片站点的抓取规则，仍可在「文档与来源」点击原图。商城加购推荐与有文档依据的配件、扩展接口分开展示。例如 R1125-10 有 25 项手册记录，另外还有 2 个商城加购项。[在本机查看 R1125-10](http://127.0.0.1:8765/#product=113991334&tab=accessories)

本轮发现 **12,939 个不同的资料网址**。其中 3,297 个因来源、类型或访问限制仅保留链接。**9,642 个应核的官方资料网址均已尝试**，**7,290 个完成目标内容筛查**，**2,352 个未能读全**。其中 969 份受文件保护、939 份无可用文字层、62 份仅部分 OCR、212 个文件不存在、150 个拒绝访问，其余 20 个有其他来源问题。另对可能涉及报价的 9 份扫描件逐页查看了 187 页。例如 `110991984` 官网箱单写螺丝 4 颗，装配步骤 4 标注用量为 6 颗，工作台并列展示两处原文。[在本机查看螺丝用量对照](http://127.0.0.1:8765/#product=110991984&tab=parts)

最终快照有 3,820 款商品具备结构化规格、2,943 款具备随箱行、1,234 款关联官方 Wiki。3,470 款有关联资料，其中 3,068 款至少有一份来源完成筛查。可确认适用型号的文档贡献了 **205 款商品的 2,922 条来源记录**，含 622 组不同的主机与配件 SKU 关系。同一物料若在不同版本、安装步骤或系列手册中的说法有差异，可以分别查到适用范围与原文。[查看含 40 个可点模组 SKU 及原工作表行号的 Grove 套装](http://127.0.0.1:8765/#product=110020230&tab=parts)

- 空白表示还没有可展示的值。界面会区别「已查栏目未列出」「尚待核对」和「原表待核」。定制范围为空时，可以向工程或产品同事确认可行性。
- 商城的 *Part List* 有时是规格表。型号、内存、存储等参数与出处可在「技术规格」查看，随附物料仍在「箱内清单」。请看依据适用于具体 SKU 还是整个系列。原文没给数量时，数量栏留空。选配清单中的物料需另核是否随箱。
- 每个 SKU 最多使用一张目录主图，完全相同的 JPG 共用一份文件。Wiki、附件和 PDF 点击后访问发布方网站，有页码依据的链接会定位到相应的文件页。商品、库存和手册都有可能晚于本地快照更新。

在「技术规格」中可查看官网原表中的型号列、技术参数和硬件概览入口。「文档与来源」会标记官方 Wiki 的购买链接、各文档核对结果和可定位的 PDF 文件页。例如 EdgeLogix 的 SKU `102110773` 在官方手册第 17 页对应 8GB RAM 与 32GB eMMC。[在本机查看此型号](http://127.0.0.1:8765/#product=102110773&tab=attributes) · [Seeed 手册第 17 页](https://files.seeedstudio.com/wiki/raspberry-pi/seeed-studio-raspberry-pi-series-catalog-v1.1.pdf#page=17)

## 可选的 AI 对话

在「开发者 → 语言与 AI」选择 DeepSeek 或豆包，填写你的供应商账户可用的模型和密钥。点右下角的聊天小球，可以新建或切换会话，也可以重开以前的对话，查看回答的引用。

**点发送会向所选外部供应商发出请求，可能产生账户费用。** 先看聊天框上方显示的页面范围。本次请求可携带问题、选中的商品依据、本地人工修改、相关页面或筛选条件，以及最近最多六轮对话。在选定的定制项目中，还可能附上相关项目资料和当前未保存描述的前 1,000 个字符。请使用获准发送给该供应商的客户资料。打开聊天窗口、切换产品和浏览历史都只读本机信息。

回答可区分官方来源、本机资料、定制项目与页面上下文。向客户确认前，可以点开引用核对。已完成的问答和引用保存在本机，每段会话最多 150 轮。Windows 会使用当前用户的 DPAPI 加密所保存的模型密钥。换电脑或 Windows 账户后，请重新输入自己的密钥。[微软 DPAPI 说明](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)

## 更新商城目录

1. 打开「开发者 → 目录更新 → 检查新增与差异」，查看新增、变更及旧值与新值。
2. 可以只应用勾选的差异，也可以输入一个或多个 SKU，或选定分类后重抓。「一键全量重抓」会检查全目录，耗时可能更长。本次搜索未出现的旧 SKU 会保留，供后续复核。
3. 看进度和两个时间。「上次检查官网」是成功检查目录的时间，「上次成功写入商品」是新资料实际写入本机的时间。遇到网站限速，请等到界面标示的「可续跑时间」，再点「续跑上次任务」。任务暂存期间仍可查原目录。

更新依赖商城公开接口、网页结构和可访问的文档。网页改版后部分字段可能仍需核对。手册换版后，请重新核对原文与引用页码。

<details>
<summary>供目录维护人员使用 · 复现一次全站核对</summary>

每个采集日期使用独立临时文件夹。运行期间员工可继续使用原工作台。普通商品页按官网抓取规则逐一读取。任务中断或收到 HTTP 429 时，已经完成的 SKU 会保留在临时目录中，等到可重试时间后执行同一步即可续跑。以下命令在解压后的项目目录中用 PowerShell 运行。

```powershell
$reviewDir = Join-Path $env:TEMP "seeed-public-review"
$docDir = Join-Path $reviewDir "documents"
$pythonExe = ".\.venv\Scripts\python.exe"
& $pythonExe -m backend.bulk_catalog --stage $reviewDir
& $pythonExe -m backend.bulk_catalog --stage $reviewDir --reconcile
& $pythonExe -m backend.bulk_catalog --stage $reviewDir --pages
& $pythonExe -m backend.bulk_catalog --stage $reviewDir --assemble
& $pythonExe -m backend.bulk_catalog --stage $reviewDir --references
& $pythonExe -m backend.document_enrichment --catalog "$reviewDir\catalog.js" --links "$reviewDir\document-links.json" --output $docDir --discovered --global-catalog
& $pythonExe -m backend.document_merge --catalog "$reviewDir\catalog.js" --output $docDir
& $pythonExe -m backend.catalog_release --stage $reviewDir --documents $docDir --output "$reviewDir\reviewed\catalog.js"
```

维护电脑解析 PDF 时需要 Poppler 的 `pdftotext` 或 `pypdf`。从英文 Wiki 的购买入口补商品关联时，可用官方 Markdown 源码和 `backend.wiki_purchases`、`backend.document_wiki` 两个模块，版本号与文件映射参数请看各模块的 `--help`。结果先写入临时目录。分发新快照前应核对统计、例外、样品 SKU 和新增 JPG；完成发布及核验后可清理临时目录。

核对通过后，先让正在进行的更新任务结束，并停止此目录的助手。运行 `& $pythonExe -m backend.catalog_release --stage $reviewDir --install-reviewed "$reviewDir\reviewed\catalog.js"`，再重启助手。安装时会核对原目录的文件指纹、本轮完成情况及每张本地主图，再替换公开目录。个人资料保存在单独的文件夹中。

文档深度核对与开发者页的日常目录更新分开运行。`backend.document_enrichment` 的 `--verify-digests` 可重新核对早期缺少文件指纹的资料。Windows 上可将 Poppler 的 `pdftoppm.exe` 完整路径传给 `--ocr-scans`，并用 `--ocr-max-pages` 设置每份文件的文字识别页数上限。确认的条目保留原文链接与页码。

维护人员若已经登录 GitHub CLI，可以在文档核对命令中选择 `--host api.github.com --github-cli`。脚本使用当前账号的官方 API 额度，只读取已确认公开的 Seeed 仓库，并用 GitHub 提供的文件指纹验证内容。日常使用工作台无需 GitHub CLI 或 GitHub 账号。

</details>

## 备份、升级工作台与换机

| 要保留的资料 | 解压目录内的位置 |
| --- | --- |
| 官方基础目录与去重主图 | `data/catalog.js` 和 `data/jpg/` |
| 设置、收藏、定制项目和人工产品修改 | `.local-workbench/workbench.json` |
| 用户替换的本地商品图 | `.local-workbench/user-images/` |
| 保存的对话和引用 | `.local-workbench/chats.sqlite3` |

**个人备份**时，先让当前任务结束，运行 `Stop Assistant.cmd`，再将整个 `.local-workbench` 复制到公司允许的个人备份位置。如需保留此刻的精确目录，也备份 `data`。个人备份里可能有客户需求、聊天和加密密钥资料。请向同事分发仓库 ZIP，个人备份应避开公共压缩包、共享群和 GitHub。

**更新软件版本**时，重新下载仓库 ZIP，解压到新文件夹，在启动新版前停止旧版。用同一账户时，可先从备份中将上表列出的个人资料复制到新版对应位置，再启动新版。使用新版随附的目录，由新版启动器创建自己的 `.venv`。确认能找到一个旧收藏、项目或会话后，再决定是否归档旧版本。若版本格式存在差异，请保留原始备份。「目录更新」只更新商城资料，软件升级采用上述下载流程。

## 遇到问题

| 表现 | 可怎么处理 |
| --- | --- |
| 黑色窗口出现 `Install 64-bit Python 3.12 or 3.13`，按键后消失 | 启动器找不到受支持的 Python。按第 1 步安装或让 IT 核对版本和位数，然后关掉旧窗口，重新双击 `启动助手.cmd`。已装在自定义位置的，请 IT 将它加入 PATH。等待期间可用 `index.html` 查商品。 |
| 打开 HTML 只见标题或一直显示「载入中」 | 单独的 HTML 缺少商品目录和配套脚本。右键完整 ZIP →「全部解压」，用 Edge 或 Chrome 打开解压后的 `index.html`，确认同层有 `data` 和 `search.js`。若浏览器明确提示禁用 JavaScript，请联系 IT。 |
| 依赖下载失败、文件夹不可写或公司策略阻止运行 | 将完整包解压到可写的本地文件夹。请 IT 核对依赖下载权限或设备策略，并提供启动器报错；截图请遮住客户资料和密钥。 |
| 浏览器没打开、看到的是旧版或出现端口提示 | 启动器显示服务就绪时，打开它给出的地址。使用对应目录的 `Stop Assistant.cmd` 停止旧实例，再从要使用的文件夹启动。如果仍有端口错误，请联系 IT。 |
| 收藏或定制项目似乎不见了 | 确认浏览器地址对应本次启动器打开的本地端口，并检查所用 Windows 账户及解压目录。每个安装目录单独保存个人资料。 |
| AI 回答失败、产品资料缺失 | 检查已选的模型、供应商和密钥。产品信息可以直接打开商城 URL 或资料出处核对，在「采集概况」查看覆盖范围，或单独刷新该 SKU。 |

目录资料来自 Seeed 海外商城与官方 Wiki。商品图片、商标及链接文档遵循各自权利人的使用条款。通过英文 Wiki 购买按钮建立的关联附有本轮核对的官方源码版本。再分发素材前请查阅相应发布者的授权信息。[Seeed 海外商城](https://www.seeedstudio.com/) · [Seeed Wiki 授权信息](https://wiki.seeedstudio.com/License/) · [本轮英文 Wiki 源码版本](https://github.com/Seeed-Studio/wiki-documents/tree/c9321cc04d695f7b89ed273908558854fe00ab50/sites/en/docs)
