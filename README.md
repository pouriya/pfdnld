# File Downloader
Watches a file containing download links and runs a command to download them. The link file is in form of:  
```text
# comment
<DOWNLOAD_LINK>
<DOWNLOAD_LINK> <OUTPUT_DIRECTORY>
```  
A `DOWNLOAD_LINK` is a valid http/https download link. If the links are similar but with a range of different numbers You can use a template in form of `[[START_NUMBER-END_NUMBER]]`. For example:  
```text
http://domain.tld/foo/bar/baz/filename-[[001-117]].mkv
```  
Also the `OUTPUT_DIRECTORY` is joined with `--out-dir` parameter. After downloading and moving each downloaded file to `--out-dir`, it appends the download result to `--download-result-file`.  
For more information run `make help`.

