" pyclewn run time file
" Maintainer:   <xdegaye at users dot sourceforge dot net>
"
" Configure VIM to be used with pyclewn and netBeans
"

if exists("b:did_pyclewn")
    finish
endif
let b:did_pyclewn = 1

" pyclewn version
let g:pyclewn_version = "pyclewn-1.0"

" enable balloon_eval
if has("balloon_eval")
    set ballooneval
    set balloondelay=100
endif



