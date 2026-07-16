import sys

from study_space_api.cli import main

if __name__ == "__main__":
    sys.argv.insert(1, "backtest")
    main()
