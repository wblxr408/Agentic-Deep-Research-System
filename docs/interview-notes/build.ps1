$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
