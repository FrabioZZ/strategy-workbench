# Backtrader — optional external historical simulator

- Installed and pinned version: **1.9.78.123**.
- Author / copyright: Daniel Rodriguez; upstream module headers state Copyright (C) 2015–2023 Daniel Rodriguez.
- Package: https://pypi.org/project/backtrader/1.9.78.123/
- Source: https://github.com/mementum/backtrader
- License: **GNU General Public License version 3 or later (GPL-3.0-or-later)**, as stated in the package metadata and source headers.
- Original license copied verbatim from the installed wheel's `backtrader-1.9.78.123.dist-info/LICENSE` to `backtrader-1.9.78.123-LICENSE.txt`.
- License SHA256: `e1c0ad728983d8a57335e52cf1064f1affd1d454173d8cebd3ed8b4a72b48704`.
- Installed with `.venv/Scripts/python.exe -m pip install backtrader==1.9.78.123` on 2026-11-10 (Asia/Shanghai). Optional dependency declaration: `requirements-paper.txt`.

The workbench imports the unmodified upstream package. Its adapter subclasses DataBase, Strategy and CommInfoBase and calls Cerebro/BackBroker directly. It does not copy or rename the workbench's existing matching engine as Backtrader.

This is GPL software, not MIT/permissive software. Keep the upstream license and notices; any onward distribution must comply with the applicable GPL source and license requirements. This notice does not relicense unrelated project files or claim that a proprietary combined distribution is permitted.

The comparison-only candidate VeighNa PaperAccount is MIT licensed (https://github.com/vnpy/vnpy_paperaccount/blob/main/LICENSE). No code from that candidate is included.
