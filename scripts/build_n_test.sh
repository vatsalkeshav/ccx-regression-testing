CCX_SRC="$HOME/ccextractor-z" 
# CCX_SRC="$HOME/s04e09" # important: this should point to the CCExtractor source code directory

# binary loc
BINARYBASE="$HOME/upsidedown/binaries"
NEWCCXR="$BINARYBASE/newccxr"
MASTERCCXR="$BINARYBASE/masterccxr"

function ccxrb() {

echo '--------------------------------- Rebuilding CCExtractor ---------------------------'

current_dir="$PWD"

cd "$CCX_SRC" || return 1

# CLEAN PREV BUILD
rm -rf build
echo '---------------------------------- Old build removed --------------------------------'

mkdir build && cd build || return 1

# BUILD
if ! cmake ../src/ || ! make; then
    echo '------------------------------ Build failed (cmake/make) ------------------------------'
    cd "$current_dir"
    return 1
fi

# VERIFY AND COPY BINARY
if ./ccextractor --version | grep -q "CCExtractor detailed version info"; then
    
    branch=$(git -C "$CCX_SRC" rev-parse --abbrev-ref HEAD)

    if [ "$branch" = "master" ]; then
        rm -f "$MASTERCCXR/ccextractor"
        cp ./ccextractor "$MASTERCCXR/"
    else
        rm -f "$NEWCCXR/ccextractor"
        cp ./ccextractor "$NEWCCXR/"
    fi

    echo '--------------------------- CCExtractor rebuilt successfully ---------------------------'
    cd "$current_dir"
    return 0
else
    echo '------------------------------ Version check failed -------------------------------------'
    cd "$current_dir"
    return 1
fi
}

# ---- first test (xds 0) start ----

function ccxtestxds0() {

# BASE DIRECTORIES
local BASE="$HOME/upsidedown/tests/xds/0"
local MASTER_OP="$BASE/master_op"
local NEW_OP="$BASE/new_op"
local DIFF="$BASE/diff"

# CLEAN OLD OUTPUT
rm -f \
  "$NEW_OP/terminal.txt" \
  "$NEW_OP/0.p1.svc01.txt" \
  "$NEW_OP/0.p1.svc02.txt" \
  "$NEW_OP/0.txt"

# RUN CCEXTRACTOR
"$NEWCCXR/ccextractor" \
  "$NEW_OP/0.ts" \
  --xds --autoprogram --out=ttxt --latin1 --ucla \
  2>&1 | tee "$NEW_OP/terminal.txt"

# CLEAN OLD DIFF
rm -f \
  "$DIFF/diff_terminal.txt" \
  "$DIFF/diff_0.p1.svc01.txt" \
  "$DIFF/diff_0.p1.svc02.txt" \
  "$DIFF/diff_0.txt"

# GENERATE DIFF
diff "$MASTER_OP/terminal.txt" "$NEW_OP/terminal.txt" \
  > "$DIFF/diff_terminal.txt"

diff -y -W 1000 \
  "$MASTER_OP/0.p1.svc01.txt" "$NEW_OP/0.p1.svc01.txt" \
  > "$DIFF/diff_0.p1.svc01.txt"

diff -y -W 1000 \
  "$MASTER_OP/0.p1.svc02.txt" "$NEW_OP/0.p1.svc02.txt" \
  > "$DIFF/diff_0.p1.svc02.txt"

diff -y -W 750 \
  "$MASTER_OP/0.txt" "$NEW_OP/0.txt" \
  > "$DIFF/diff_0.txt"
}

# ---- Second test (xds 1) start ----

function ccxtestxds1() {

# BASE DIRECTORIES
local BASE="$HOME/upsidedown/tests/xds/1"
local MASTER_OP="$BASE/master_op"
local NEW_OP="$BASE/new_op"
local DIFF="$BASE/diff"

# CLEAN OLD OUTPUT
rm -f \
  "$NEW_OP/terminal.txt" \
  "$NEW_OP/1.p1.svc01.txt" \
  "$NEW_OP/1.txt"

# RUN CCEXTRACTOR
"$NEWCCXR/ccextractor" \
  "$NEW_OP/1.ts" \
  --xds --autoprogram --out=ttxt --latin1 --ucla \
  2>&1 | tee "$NEW_OP/terminal.txt"

# CLEAN OLD DIFF
rm -f \
  "$DIFF/diff_terminal.txt" \
  "$DIFF/diff_1.p1.svc01.txt" \
  "$DIFF/diff_1.txt"

# GENERATE DIFF
diff "$MASTER_OP/terminal.txt" "$NEW_OP/terminal.txt" \
  > "$DIFF/diff_terminal.txt"

diff -y -W 1000 \
  "$MASTER_OP/1.p1.svc01.txt" "$NEW_OP/1.p1.svc01.txt" \
  > "$DIFF/diff_1.p1.svc01.txt"

diff -y -W 750 \
  "$MASTER_OP/1.txt" "$NEW_OP/1.txt" \
  > "$DIFF/diff_1.txt"
}

# ---- third test (isdb 0) start ----

function ccxtestisdb0() {

# BASE DIRECTORIES
local BASE="$HOME/upsidedown/tests/isdb/0"
local MASTER_OP="$BASE/master_op"
local NEW_OP="$BASE/new_op"
local DIFF="$BASE/diff"

#  CLEAN OLD OUTPUT 
rm -f \
  "$NEW_OP/terminal.txt" \
  "$NEW_OP/0.txt" \
  "$NEW_OP/0.srt"

#  RUN CCEXTRACTOR 
"$NEWCCXR/ccextractor" \
  "$NEW_OP/0.mpg" \
  2>&1 | tee "$NEW_OP/terminal.txt"

"$NEWCCXR/ccextractor" \
  "$NEW_OP/0.mpg" \
   --datets --ttxt --utf8 --levdistmincnt 2 --levdistmaxpct 10 --unixts 0

# CLEAN OLD DIFF 
rm -f \
  "$DIFF/diff_terminal.txt" \
  "$DIFF/diff_0_srt.txt" \
  "$DIFF/diff_0_txt.txt"

# GENERATE DIFF
diff "$MASTER_OP/terminal.txt" "$NEW_OP/terminal.txt" \
  > "$DIFF/diff_terminal.txt"

# diff -y -W 1000 \
diff "$MASTER_OP/0.txt" "$NEW_OP/0.txt" \
  > "$DIFF/diff_0_txt.txt"

# diff -y -W 1000 \
diff "$MASTER_OP/0.srt" "$NEW_OP/0.srt" \
  > "$DIFF/diff_0_srt.txt"

}

# ---- fouth test (isdb 1) start ----

function ccxtestisdb1() {

# BASE DIRECTORIES
local BASE="$HOME/upsidedown/tests/isdb/1"
local MASTER_OP="$BASE/master_op"
local NEW_OP="$BASE/new_op"
local DIFF="$BASE/diff"

#  CLEAN OLD OUTPUT 
rm -f \
  "$NEW_OP/terminal.txt" \
  "$NEW_OP/1.txt"

#  RUN CCEXTRACTOR 
"$NEWCCXR/ccextractor" \
  "$NEW_OP/1.mpg" \
  2>&1 | tee "$NEW_OP/terminal.txt"

# CLEAN OLD DIFF 
rm -f \
  "$DIFF/diff_terminal.txt" \
  "$DIFF/diff_1.txt"

# GENERATE DIFF
diff "$MASTER_OP/terminal.txt" "$NEW_OP/terminal.txt" \
  > "$DIFF/diff_terminal.txt"

diff "$MASTER_OP/1.srt" "$NEW_OP/1.srt" \
  > "$DIFF/diff_1.txt"

}
