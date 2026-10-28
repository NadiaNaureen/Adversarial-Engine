param([string]$InputDocument,[string]$OutputPdf)
$revisionWord = New-Object -ComObject Word.Application
$revisionWord.Visible = $false
$revisionWord.DisplayAlerts = 0
try {
    $revisionDoc = $revisionWord.Documents.Open($InputDocument, $false, $true)
    $revisionDoc.Repaginate()
    Write-Output ('Pages: ' + $revisionDoc.ComputeStatistics(2))
    $revisionDoc.ExportAsFixedFormat($OutputPdf,17)
    $revisionDoc.Close(0)
} finally {
    $revisionWord.Quit()
}
