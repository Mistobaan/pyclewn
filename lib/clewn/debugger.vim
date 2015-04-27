" vi:set ts=8 sts=4 sw=4 et tw=80:
" Pyclewn commands and autocommands.

" Set 'cpo' option to its vim default value.
let s:cpo_save=&cpo
set cpo&vim

let s:bufList = {}
let s:bufLen = 0

function! s:error(msg)
    echohl ErrorMsg
    echo a:msg
    call inputsave()
    call input("Press the <Enter> key to continue.")
    call inputrestore()
    echohl None
endfunction

" Build the list as an hash of active buffers This is the list of buffers loaded
" on startup, that must be advertized to pyclewn.
function! s:BuildList()
    let wincount = winnr("$")
    let index = 1
    while index <= wincount
        let s:bufList[expand("#". winbufnr(index) . ":p")] = 1
        let index = index + 1
    endwhile
    let s:bufLen = len(s:bufList)
endfunction

" Return true when the buffer is in the list, and remove it.
function! s:InBufferList(pathname)
    if s:bufLen && has_key(s:bufList, a:pathname)
        unlet s:bufList[a:pathname]
        let s:bufLen = len(s:bufList)
        return 1
    endif
    return 0
endfunction

" Function that can be used for testing Remove 's:' to expand function scope to
" runtime.
function! s:PrintBufferList()
    for key in keys(s:bufList)
       echo key
    endfor
endfunction

" Send the open/close event for this clewn buffer.
function! s:bufwin_event(fullname, state)
    let l:regexp = '^(clewn)_\(.\+\)$'
    let l:name = substitute(a:fullname, l:regexp , '\1', "")
    if l:name == a:fullname
        return
    endif

    " Send the event, but not for the empty buffer.
    if l:name != "empty"
        exe "nbkey ClewnBuffer." . l:name . "." . a:state
    endif
endfunction

" Send a TabPage event.
function! s:tabpage_event()
    let l:state = "close"
    let l:regexp = '^(clewn)_\(.\+\)$'
    for l:nr in tabpagebuflist()
        let l:bufname = bufname(l:nr)
        let l:name = substitute(l:bufname, l:regexp , '\1', "")
        " The console or one of the list buffers except '(clewn)_variables'
        if l:name != l:bufname && l:name != "empty" && l:name != "variables"
            let l:state = "open"
            break
        endif
    endfor

    " Send the event.
    exe "nbkey ClewnBuffer.TabPage." . l:state
endfunction

" Popup gdb console on pyclewn mapped keys.
function! s:mapkeys()
    call s:nbcommand("mapkeys")
endfunction

augroup clewn
    autocmd!
    autocmd BufEnter (clewn)_* silent! setlocal bufhidden=hide
    autocmd BufEnter (clewn)_* silent! setlocal buftype=nofile
    autocmd BufEnter (clewn)_* silent! setlocal noswapfile
    autocmd BufEnter (clewn)_* silent! setlocal fileformat=unix
    autocmd BufEnter (clewn)_* silent! setlocal expandtab
    autocmd BufWinEnter (clewn)_* setlocal nowrap

    if ! %(noname_fix)s
        autocmd VimEnter * silent! call s:BuildList()
        autocmd BufWinEnter * silent! call s:InBufferList(expand("<afile>:p"))
    endif

    autocmd BufWinEnter (clewn)_* silent! call s:bufwin_event(expand("<afile>"), "open")
    autocmd BufWinLeave (clewn)_* silent! call s:bufwin_event(expand("<afile>"), "close")
    autocmd TabEnter * call s:tabpage_event()
    autocmd BufWinEnter * call s:restore_clewn_window(expand("<afile>"))
    if "%(window)s" == "none"
        autocmd BufWinEnter (clewn)_console normal G
    endif
augroup END

function! s:restore_clewn_window(name)
    if ! exists("w:pyclewn_window") || a:name =~# "^(clewn)_"
        return
    endif

    " A BufWinEnter event in a clewn window whose content is not a clewn buffer.
    " Restore the window and load the buffer in the first non clewn window.
    edit #

    for l:tabidx in range(tabpagenr('$'))
        let l:tabno = l:tabidx + 1
        exe "tabnext " . l:tabno
        for l:winidx in range(tabpagewinnr(l:tabno, '$'))
            let l:winno = l:winidx + 1
            exe l:winno . "wincmd w"
            if ! exists("w:pyclewn_window")
                exe "edit " . a:name
                return
            endif
        endfor
    endfor
endfunction

" The Funcref dictionary of functions to be run only once.
let s:runonce_dict = {}

" Create the windows.
function! s:runonce_dict.create_windows() dict
    if pyclewn#version#RuntimeVersion() != "%(runtime_version)s"
        nbclose
        let l:msg = "Error: the version of the Vim runtime files does "
        let l:msg .= "not match Pyclewn version.\n"
        let l:msg .= "Please re-install the Pyclewn vimball with:\n\n"
        let l:msg .= "  python -c \"import clewn; clewn.get_vimball()\"\n"
        let l:msg .= "  vim -S pyclewn-%(version)s.vmb\n\n"
        call s:error(l:msg)
    else
        call pyclewn#buffers#CreateWindows("%(debugger)s", "%(window)s")
    endif
endfunction

" Send fake fileOpened events for all the buffers existing at the start of the
" netbeans session.
function! s:runonce_dict.send_fake_fileopened_evts() dict
    for l:idx in range(bufnr('$'))
        let l:name = bufname(l:idx + 1)
        if l:name != ""
            exe "nbkey fakeFileOpened." . l:name
        endif
    endfor
endfunction

" Run the nbkey netbeans Vim command.
function! s:nbcommand(...)
    if !has("netbeans_enabled")
        call s:error("Error: netbeans is not connected.")
        return
    endif

    " Run all the 'runonce_dict' functions using their Funcref.
    for key in keys(s:runonce_dict)
        call s:runonce_dict[key]()
    endfor
    let s:runonce_dict = {}

    " Allow '' as first arg: the 'C' command followed by a mandatory parameter
    if a:0 != 0
        if a:1 != "" || (a:0 > 1 && a:2 != "")
            if %(getLength_fix)s
                if a:1 == "dbgvar"
                    call pyclewn#buffers#DbgvarSplit()
                endif
            endif
            let cmd = "nbkey " . join(a:000, ' ')
            exe cmd
        endif
    endif
endfunction

if ! %(noname_fix)s
    " Run the nbkey netbeans Vim command.
    function! s:nbcommand(...)
        if !has("netbeans_enabled")
            call s:error("Error: netbeans is not connected.")
            return
        endif

        " Run all the 'runonce_dict' functions using their Funcref.
        for key in keys(s:runonce_dict)
            call s:runonce_dict[key]()
        endfor
        let s:runonce_dict = {}

        if bufname("%%") == ""
            let l:msg = "Cannot run a pyclewn command on the '[No Name]' buffer.\n"
            let l:msg .= "Please edit a file first."
            call s:error(l:msg)
            return
        endif

        " Allow '' as first arg: the 'C' command followed by a mandatory parameter
        if a:0 != 0
            if a:1 != "" || (a:0 > 1 && a:2 != "")
                " edit the buffer that was loaded on startup and call input() to
                " give a chance for vim72 to process the putBufferNumber netbeans
                " message in the idle loop before the call to nbkey
                let l:currentfile = expand("%%:p")
                if s:InBufferList(l:currentfile)
                    exe "edit " . l:currentfile
                    echohl WarningMsg
                    echo "Files loaded on Vim startup must be registered with pyclewn."
                    echo "Registering " . l:currentfile . " with pyclewn."
                    call inputsave()
                    call input("Press the <Enter> key to continue.")
                    call inputrestore()
                    echohl None
                endif
                if %(getLength_fix)s
                    if a:1 == "dbgvar"
                        call pyclewn#buffers#DbgvarSplit()
                    endif
                endif
                let cmd = "nbkey " . join(a:000, ' ')
                exe cmd
            endif
        endif
    endfunction
endif

" unmapkeys function.
function s:unmapkeys()
    for l:key in [%(mapkeys)s]
        try
           exe "unmap " . l:key
        catch /.*/
        endtry
    endfor
endfunction

" exitclewn function.
function s:exitclewn()
    nbclose

    " Remove the Pyclewn buffers.
    for l:idx in range(bufnr('$'))
        let l:bufno = l:idx + 1
        if bufname(l:bufno) =~# "^(clewn)_"
            exe l:bufno . "bwipeout"
        endif
    endfor
endfunction

" The commands.
%(commands)s

" The debugger specific part.
%(debugger_specific)s

" Create the windows layout.
" The windows are created only at the first command instead of on startup, when
" '--window=usetab' is set and pyclewn is not started from Vim to workaround the
" problem that the cursor is set in the clewn tab page at the first command in
" that case.
if has("netbeans_enabled") || ! %(usetab)s
    call s:runonce_dict.create_windows()
    unlet s:runonce_dict.create_windows
    if has("netbeans_enabled")
        call s:runonce_dict.send_fake_fileopened_evts()
        unlet s:runonce_dict.send_fake_fileopened_evts
    endif
endif

let &cpo = s:cpo_save

" Delete the vim script after it has been sourced.
call delete(expand("<sfile>"))

