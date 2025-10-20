$stamp = (Get-Date).ToString("yyyyMMdd-HHmm")
Compress-Archive -Path .\* -DestinationPath "..\crypto-agents-baseline-$stamp.zip" -Force
