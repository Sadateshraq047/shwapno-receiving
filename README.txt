RECEIVING WATCH - HOW TO UPDATE IT YOURSELF
============================================

What is in this folder (D:\pc2\RecvDash)
  index.html               the dashboard page (you never edit this for a normal update)
  data\                    the numbers the page reads (meta.json + one file per Sunday opening)
  build_receiving_data.py  reads MySQL (pc2) + your Excel dimensions and writes data\
  make_demo_data.py        makes fake demo data, only for previewing the layout
  update_dashboard.bat     the one you double-click every time you refresh
  open_dashboard.bat       shows the dashboard on your PC
  publish.bat              sends index.html + data\ to GitHub
  setup_once.bat           installs Python packages (first time only)
  setup_github_once.bat    connects this folder to GitHub (first time only)

FIRST TIME ONLY
  1. Double-click setup_once.bat. Wait for it to finish with no red errors.
  2. Double-click open_dashboard.bat. Your browser opens the dashboard with DEMO data
     (the yellow bar says so). Close the black window when you are done.
  3. Optional, to publish on the web: double-click setup_github_once.bat and follow the
     on-screen steps. You need git installed and a GitHub account.

EVERY TIME YOU WANT FRESH DATA
  1. Make sure MySQL is running and the tables (sales, stock, receiving) are loaded up to the
     closing day you want. The dashboard closing date is the latest date found in the data.
  2. Double-click update_dashboard.bat.
  3. Type the MySQL root password when asked (it is not saved).
  4. Wait. It prints one line per Sunday opening, for example:
        2026-09-27: 123,554 pairs | over 22,117 | under 4,475
     The slowest parts are reading the big sales and stock tables. Expect several minutes.
  5. When it asks "Publish to GitHub now? (Y/N)": type N to check first, Y to publish.
  6. To check on your PC: double-click open_dashboard.bat.

WHAT THE SCRIPT DECIDES FOR YOU
  Closing date   = the earlier of the latest stock date and the latest sales date. Fixed, nobody
                   can change it on the page.
  Window         = starts on the first Sunday on or after (closing minus 2 months).
  Opening dates  = every Sunday in the window, up to the Sunday before closing.
  So each week the oldest Sunday drops off and the new closing day moves forward.

THE DIMENSION FILES
  Dimensions come from D:\pc2\SDT_Database_Template (2).xlsx, sheets DimArticle and DimOutlet.
  When you add a new article or outlet, add it to those sheets and save/close the file, then run
  update_dashboard.bat. Articles or outlets that are not in the sheets are ignored (the same
  as in Power BI). Keep ArticleNo and OutletCode as text. Please fill Category3, MasterCategory
  and "No. Of Std Stock Days" - articles without standard days get an estimated closing stock of 0.

HOW THE NUMBERS ARE CALCULATED (same rules as the Power BI report)
  Per outlet + article, for the chosen opening date up to the closing date:
   Average sales      = all sales in the window / days from its first sale to its last sale
   Total inventory    = opening stock (on the opening Sunday) + units received
   Est. closing stock = average sales x standard stock days
   Overstock          = inventory - sales - est. closing stock
   Over receiving     = the smaller of overstock and units received (only when overstock > 0)
   Over score         = over qty x 3 / units received. Counted only when units received > 10,
                        and the first receipt is at least 7 days before the latest posting date.
   Under receiving    = the shortfall, when inventory - sales - est. closing stock < 0.
                        Articles with more than 100 standard days use 100 days of average sales.
   Under score        = shortfall x 3 / (sales + est. closing stock), capped at 3. Counted only when
                        sales > 10 and inventory >= 5.
   Value (BDT)        = over qty x cost per unit (COGS / units sold, or receiving amount / units received)
   Incident rate      = incidents / outlet-article pairs that received stock in the period.
  Receiving rows with movement type 303 and a positive quantity are left out, as in Power BI.

SETTINGS YOU CAN CHANGE (top of build_receiving_data.py, the CFG block)
  user / host / port / db    MySQL connection
  dim_xlsx                   the Excel file with DimArticle and DimOutlet
  window_months              2 = two months
  closing_override           for example "2026-11-15" to rebuild an earlier closing date
  max_rows_per_table         how many incidents the table lists per opening (the cards, map and
                             charts always count everything)
  To avoid typing the password each time, set a Windows environment variable named MYSQL_PWD.

IF SOMETHING GOES WRONG
  "No module named ..."      run setup_once.bat again
  "Access denied"            wrong MySQL password or user
  Dashboard says data could not be loaded
                             open it with open_dashboard.bat, not by double-clicking index.html
  The page looks empty       check that data\meta.json exists; run update_dashboard.bat again
  Excel file is locked       close the Excel file and run again
  Numbers differ from Power BI
                             average sales here use the 2-month window; Power BI used its loaded range

BEFORE YOU PUBLISH ON GITHUB
  GitHub Pages on a free account needs a public repository, so anyone with the link can open the
  page and download the data folder. The page shows outlet names, article names, quantities and
  values. Publish only if that is acceptable for Shwapno, or use a private repository with a
  paid GitHub plan, or keep the dashboard on your own network and use only open_dashboard.bat.
