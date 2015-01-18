" vi:set ts=8 sts=2 sw=2 et tw=80:
" Pyclewn run time file.
" Maintainer:   <xdegaye at users dot sourceforge dot net>
"
" Configure VIM to be used with pyclewn and netbeans.
"
if exists("s:did_pyclewn")
    finish
endif
let s:did_pyclewn = 1

" The following global variables define how pyclewn is started. They may be
" changed to suit your preferences.
function s:init()
    if exists("g:pyclewn_python")
      let s:pgm = g:pyclewn_python
    else
      let s:pgm = "python"
    endif

    if exists("g:pyclewn_args")
      let s:args = g:pyclewn_args
    else
      let s:args = "--window=top --maxlines=10000 --background=Cyan,Green,Magenta"
    endif

    if exists("g:pyclewn_connection")
      let s:connection = g:pyclewn_connection
    else
      let s:connection = "localhost:3219:changeme"
    endif

    " Uncomment the following line to print full traces in a file named
    " 'logfile' for debugging purpose (or change g:pyclewn_args).
    " let s:args .= " --level=nbdebug --file=logfile"

    let s:fixed = "--daemon --editor= --netbeans=" . s:connection . " --cargs="
endfunction

" Run the 'Cinterrupt' command to open the console.
function s:interrupt(args)
    " find the prefix
    let argl = split(a:args)
    let prefix = "C"
    let idx = index(argl, "-x")
    if idx == -1
        let idx = index(argl, "--prefix")
        if idx == -1
            for item in argl
                if stridx(item, "--prefix") == 0
                    let pos = stridx(item, "=")
                    if pos != -1
                        let prefix = strpart(item, pos + 1)
                    endif
                endif
            endfor
        endif
    endif

    if idx != -1 && len(argl) > idx + 1
        let prefix = argl[idx + 1]
    endif

    " hack to prevent Vim being stuck in the command line with '--More--'
    echohl WarningMsg
    echo "About to run the 'interrupt' command."
    call inputsave()
    call input("Press the <Enter> key to continue.")
    call inputrestore()
    echohl None
    exe prefix . "interrupt"
endfunction

" Check wether pyclewn successfully wrote the script file.
function s:pyclewn_ready(filename)
    let l:cnt = 1
    echohl WarningMsg
    while l:cnt < 20
        echon "."
        let l:cnt = l:cnt + 1
        if filereadable(a:filename)
            break
        endif
        sleep 200m
    endwhile
    echohl None
    if !filereadable(a:filename)
        throw "Error: pyclewn failed to start.\n\n"
    endif
    call s:info("Creation of vim script file \"" . a:filename . "\": OK.\n")
endfunction

" Start pyclewn and vim netbeans interface.
function s:start(args)
    if !exists(":nbstart")
        throw "Error: the ':nbstart' vim command does not exist."
    endif
    if has("netbeans_enabled")
        throw "Error: netbeans is already enabled and connected."
    endif
    if !executable(s:pgm)
        throw "Error: '" . s:pgm . "' cannot be found or is not an executable."
    endif
    let l:tmpfile = tempname()

    " remove console and dbgvar buffers from previous session
    if bufexists("(clewn)_console")
        bwipeout (clewn)_console
    endif
    if bufexists("(clewn)_dbgvar")
        bwipeout (clewn)_dbgvar
    endif

    " start pyclewn and netbeans
    call s:info("Starting pyclewn.\n")
    exe "silent !" . s:pgm . " -m clewn " . s:fixed . l:tmpfile . " " . a:args . " &"
    call s:info("Running nbstart, <C-C> to interrupt.\n")
    call s:pyclewn_ready(l:tmpfile)
    exe "nbstart :" . s:connection

    " source vim script
    if has("netbeans_enabled")
        " the pyclewn generated vim script is sourced only once
        if ! exists("s:source_once")
            let s:source_once = 1
            exe "source " . l:tmpfile
        endif
        call s:info("The netbeans socket is connected.\n")
        let argl = split(a:args)
        if index(argl, "pdb") == len(argl) - 1
            call s:interrupt(a:args)
        endif
    else
        throw "Error: the netbeans socket could not be connected."
    endif
endfunction

function pyclewn#StartClewn(...)
    call s:init()
    let l:args = s:args
    if a:0 != 0
      if index(["gdb", "pdb", "simple"], a:1) == -1
        call s:error("Unknown debugger '" . a:1 . "'.")
        return
      endif
      if a:0 > 1
          let l:args .= " --args \"" . join(a:000[1:], ' ') . "\""
      endif
      let l:args .= " " . a:1
    endif

    try
        call s:start(l:args)
    catch /.*/
        call s:info("The 'Pyclewn' command has been aborted.\n")
        let l:err = v:exception
        let l:argl = split(l:args)
        if index(l:argl, "pdb") == len(l:argl) - 1
            let l:err .= "Create a python script containing the line:\n"
            let l:err .= "   import clewn.vim as vim; vim.pdb(level='debug')\n"
            let l:err .= "and run this script to get the cause of the problem."
        else
            let l:err .= "Run 'python -m clewn' to get the cause of the problem."
        endif
        call s:error(l:err)
        " vim console screen is garbled, redraw the screen
        if !has("gui_running")
            redraw!
        endif
        " clear the command line
        echo "\n"
    endtry
endfunction

function s:info(msg)
    echohl WarningMsg
    echo a:msg
    echohl None
endfunction

function s:error(msg)
    echohl ErrorMsg
    echo a:msg
    call inputsave()
    call input("Press the <Enter> key to continue.")
    call inputrestore()
    echohl None
endfunction
