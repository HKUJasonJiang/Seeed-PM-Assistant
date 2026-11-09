# Seeed PM Assistant

[简体中文](README.zh-CN.md)

A local Windows workbench for Seeed project managers. Start with a customer’s SKU, model or application requirement. Compare products from the **international Seeed Studio store**, check what ships in the box, find regional accessory SKUs and collect customization requests. The included catalogue works without an AI key.

## First-time setup on Windows

1. **Check your PC and Python.** Use Windows 10 or 11 on an x64 PC and a browser. Open the Start menu, type `cmd`, select **Command Prompt**, then run `py -3 --version` or `python --version`. If you already have **64-bit CPython 3.12 or 3.13**, skip installation and go to step 2. Otherwise ask IT to install it. On a self-managed PC, download a 3.13.x **Windows installer (64-bit)** from Python.org. On the traditional installer’s first screen, select **Add python.exe to PATH**, then **Install Now**. Open a fresh Command Prompt and repeat the version check. If the only result is the Microsoft Store, contact IT. [Python for Windows](https://www.python.org/downloads/windows/) · [Python installation guide](https://docs.python.org/3.13/using/windows.html)
2. **Download the project ZIP (about 100 MB).** Use the direct download below, or open the repository and select **Code → Download ZIP** above the file list. Wait for the download to finish. If your company network blocks GitHub, ask IT for the ZIP through an approved channel. The ZIP workflow requires no Git, Node.js or Codex installation. [Download the latest ZIP](https://github.com/HKUJasonJiang/Seeed-PM-Assistant/archive/refs/heads/main.zip) · [Project repository](https://github.com/HKUJasonJiang/Seeed-PM-Assistant) · [GitHub download instructions](https://docs.github.com/en/repositories/working-with-files/using-files/downloading-source-code-archives)
3. **Extract the whole ZIP.** In File Explorer, right-click the ZIP and select **Extract All…**. Choose a writable folder owned by your Windows account, outside cloud sync and shared drives. For example, type `%USERPROFILE%` into the File Explorer address bar, create a `SeeedTools` folder there, then browse to it in the extraction dialog. Open the extracted subfolder containing `Start Assistant.cmd`, `index.html` and `data`. Keep that folder together. [Microsoft’s extraction guide](https://support.microsoft.com/en-us/windows/experience/storage-filemanagement/zip-and-unzip-files)
4. **Double-click `Start Assistant.cmd`.** The Chinese launcher `启动助手.cmd` opens the same workbench. On first launch it creates a private `.venv` folder in this installation and installs Pillow 12.3.0 and lxml 6.1.3, the versions pinned for this build. Allow time for the first download using your organisation’s approved network. Later launches reuse the installed packages. Bookmark the address the launcher opens. The default is `http://127.0.0.1:8765/`. If the default port is busy, the launcher can select a free local port. This address serves only your own PC. [Open the default local address](http://127.0.0.1:8765/)

**Check your installation.** Search for `100025879`. The first card should be **reComputer R1014-10**, with **2 GB RAM and 16 GB eMMC**. Open **In the box** and follow the source beside the five 120 Ω termination resistors. You can inspect the catalogue offline after setup. Opening an official source, checking the store for updates or sending an AI message requires a connection. [Open the sample on the default port](http://127.0.0.1:8765/#product=100025879&tab=parts)

To finish for the day, close the browser tab. To stop the local service, double-click `Stop Assistant.cmd` in the installation you started. It checks that the service belongs to this copy and leaves active work running. If it reports a busy operation, let it finish and run Stop again. Opening `index.html` directly provides a read-only catalogue. Use the launcher for saved work, updates and conversations.

## Use it for a customer request

| Your task | In the workbench |
| --- | --- |
| Identify a product or suggest an alternative | In **Product finder**, enter a SKU, model or need such as `J4012, need Super mode`. A specified product stays on the first card. A family name can show a representative configuration. Check the SKU and the stated reason for each alternative. The search rules are available beneath the search box. |
| Prepare a quotation | Open the full store URL at the top of the card. Read the listing currency, price or range and snapshot date. Confirm the current price, stock, quantity pricing and any customization charges with the relevant sales channel before quoting. A blank price means the workbench has no usable figure. |
| Check package contents and expansion | Use **In the box**, **Accessories**, **Options & exclusions** and **Documents & sources**. Watch for region, interface, power adapter and SKU differences. Try `R1100 with EU868` and compare the SPI module `114993268` with the USB module `114992628`. A handbook page or suggested add-on can have different scope from a SKU-specific packing list. |
| Track items and a custom request | Use the star on a product card. The sidebar arrow collapses the favorites list. In **Customization**, create a project with a title, requirements, labels and one or more eligible SKUs. Eligibility comes from applicable manufacturer evidence or an explicit local confirmation. |
| Edit a local record or change language | Open **Developer → Product editor** to add a SKU, correct details or replace the main image. Local edits keep priority after a store refresh. For English or Simplified Chinese, use **Developer → Language & AI**. Product names, quoted source text and your own entries keep their original language. |

### What the included catalogue covers

The **8 November 2026** snapshot contains **4,499 unique SKUs** from the overseas public store. **1,776** map to the 15 menu categories checked. The remaining SKUs are still searchable. **4,494** have a positive starting price, **4,467** have a local main image, **2,829** have one or more recorded in-box items, and **959** have document links. Detailed product-page sections were captured on **395** SKUs. **Coverage** shows the counts for the version you are using.

- An empty field means there is no recorded value. The interface distinguishes a checked section with no entry, a section awaiting verification and raw rows that require review. An empty customization field does not establish whether engineering can offer a service.
- The store’s *Part List* can contain specifications. The workbench displays identifiable attributes and package contents separately. Check the source and whether it applies to the SKU or the family. Some manufacturers list equipment without a quantity. An accessory listing alone does not establish that the accessory ships with the product.
- Each SKU uses at most one catalogue main image. Identical JPEGs share a file. Wiki pages and PDF manuals open at the publisher. Verified PDF references can land on a specific file page. The store, its stock and the manuals can change after the snapshot.

## Optional AI conversations

In **Developer → Language & AI**, choose DeepSeek or Doubao, supply a model your provider account can access, and enter your own API key. Open the floating chat button at the bottom right. You can start a conversation, switch among saved conversations and follow sources in an answer.

**Sending a message contacts the selected external provider** and may incur charges on that account. Before sending, check the context shown above the chat. A request can include your question, selected product evidence, local product edits, relevant page or filter information, and up to six earlier turns. On a selected customization project it can also include relevant project details and up to 1,000 characters of the current unsaved draft description. Use customer information approved for that provider. Opening the panel, browsing history or switching products reads local data.

Answers identify official sources, local records and project or page context where available. Check those references before making a customer commitment. Completed turns and citations are stored on this PC. A conversation holds up to 150 turns. A saved provider key is protected by Windows DPAPI for the current user. When moving to another PC or Windows account, enter your own key again. [Microsoft’s explanation of DPAPI](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)

## Update the store catalogue

1. Go to **Developer → Catalog updates → Check for changes**. Review new and changed records and their old and new values.
2. Apply selected differences or refresh specific SKUs or a category. **Run full refresh** requests the whole catalogue and can take considerably longer. Earlier records that disappear from a search are retained for review.
3. Watch the progress and the two dates. **Last store check** records a successful check. **Last successful catalog write** records when product data was applied. If the store rate-limits requests, wait until **Resume after**, then use **Resume job**. The previous catalogue remains available while work is staged.

Updates depend on the public store’s page layouts, search interface and available documents. A changed page may leave fields pending. Recheck manufacturer links and PDF pages when a manual changes.

## Back up, update the app or change PCs

| What to keep | Location inside the extracted folder |
| --- | --- |
| Official catalogue and deduplicated main images | `data/catalog.js` and `data/jpg/` |
| Local settings, favorites, projects and product edits | `.local-workbench/workbench.json` |
| Locally supplied product images | `.local-workbench/user-images/` |
| Completed conversations and citations | `.local-workbench/chats.sqlite3` |

**For a private backup**, finish running tasks, run `Stop Assistant.cmd`, and copy `.local-workbench` to an approved private backup location. To preserve your exact catalogue as well, copy `data` with it. The backup can contain customer requirements, chats and encrypted credential material. Give colleagues the repository ZIP for installation and keep your personal backup out of shared archives and GitHub.

**To update the application**, download the new ZIP and extract it to a separate folder. Stop the old installation before starting the new one. On the same account, copy the personal items listed in the table from your backup into the matching locations in the new folder before first launch. Use the new installation’s own catalogue and let its launcher build its own `.venv`. Check one favorite, project or previous chat before retiring the old copy. Keep your original backup if formats differ between releases. Catalogue updates in Developer do not install new application code.

## If something goes wrong

| Symptom | What to do |
| --- | --- |
| Python missing, package download fails or Windows blocks the launcher | Make sure you extracted all files. Check Python as in step 1. Give IT the exact launcher message and ask them to verify the Python installation, package access or device policy. Omit customer data and keys from screenshots. |
| The browser does not open, the port is occupied, or the wrong copy appears | If the launcher says it is ready, open the local address it reports. For a previous installation, run **its own** `Stop Assistant.cmd`, then start the intended copy. If a port error persists, contact IT. |
| Favorites or projects seem to be missing | Confirm the browser address uses the local port your launcher opened, and that you launched the same extracted folder under the same Windows account. Personal data lives with that installation. |
| An AI answer or product detail is unavailable | Check the selected provider, model and key. For the product, use its store URL and source links, inspect the coverage status, or request a scoped refresh. |

The catalogue uses public material from the Seeed international store and Seeed Studio Wiki. Product images, trademarks and linked documents remain subject to their respective owners’ terms. Confirm permission with the owner before republishing material or redistributing the software beyond the intended team. [Seeed international store](https://www.seeedstudio.com/) · [Seeed Studio Wiki](https://wiki.seeedstudio.com/)
