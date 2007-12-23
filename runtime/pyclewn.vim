" pyclewn run time file
" Maintainer:   <xdegaye at users dot sourceforge dot net>
"
" Configure VIM to be used with pyclewn and netBeans
"
" $Id: pyclewn.vim 175 2007-11-01 19:12:22Z xavier $

if exists("b:did_pyclewn")
    finish
endif
let b:did_pyclewn = 1

" pyclewn version
let g:pyclewn_version = "pyclewn-0.2"

" enable balloon_eval
if has("balloon_eval")
    set ballooneval
    set balloondelay=100
endif



