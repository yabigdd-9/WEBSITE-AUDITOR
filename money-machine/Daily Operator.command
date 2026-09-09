#!/bin/bash
set -eu
"$HOME/MoneyMachine/mm" daily
open "$HOME/MoneyMachine/reports/daily-operator/index.html"
