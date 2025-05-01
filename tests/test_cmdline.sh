#! /bin/bash

MSGL="python -m msglen"

test_wrap_unwrap1() {
    echo MSGL=$MSGL
    echo "Test" | $MSGL wrap --param name=value a=1 -s 232323=2323 -p msgd | $MSGL unwrap
    assertEquals "0" "$?"
}

test_wrap_unwrap2() {
    echo MSGL=$MSGL
    data=$(echo "Test" | $MSGL wrap --param name=value a=1 -s 232323=2323 -p msgd | $MSGL unwrap)
    assertEquals "0" "$?"
    assertEquals "Test" "$data"
}

_test_wrap_unwrap3() {
    echo MSGL=$MSGL
    data=$($MSGL wrap -m test --param name=value a=1 -s 232323=2323 -p msgd | $MSGL unwrap)
    assertEquals "0" "$?"
    assertEquals "Test" "$data"
}

test_wrap_unwrap_lines1() {
    (echo "a"; echo "b"; sleep 1; echo "a"; echo "b"; ) |\
        $MSGL wraplines --param name=value a=1 -s 232323=2323 -p msgd | $MSGL unwraplines
    assertEquals "0" "$?"
}

test_wrap_unwrap_lines2() {
    (echo "a"; echo "b"; sleep 1; echo "a"; echo "b"; ) |\
        $MSGL wraplines --param name=value a=1 -s 232323=2323 -p msgd | $MSGL unwraplines -g
    assertEquals "2" "$?"
}

test_wrap1() {
    echo MSGL=$MSGL
    echo "Test" | $MSGL wrap --param name=value a=1 -s 232323=2323 -p msgd
    assertEquals "0" "$?"
}

test_wrap_file_small() {
    echo MSGL=$MSGL
    cat /dev/urandom | head -c 10000 > in.dat
    cat in.dat | $MSGL wrap -p msgd -o out.dat
    assertEquals "0" "$?"
    cat out.dat | $MSGL -l -d -o ret.dat
    assertEquals "0" "$?"
    insz=$(wc -c in.dat | awk '{print $1}')
    outsz=$(wc -c out.dat | awk '{print $1}')
    retsz=$(wc -c ret.dat | awk '{print $1}')
    assertEquals "10000" "$insz"
    assertEquals "10016" "$outsz"
    diff in.dat ret.dat
    assertEquals "0" "$?"
}

test_wrap_file_large() {
    echo MSGL=$MSGL
    cat /dev/urandom | head -c 1000000 > in.dat
    cat in.dat | $MSGL wrap -p msgd -o out.dat
    assertEquals "0" "$?"
    cat out.dat | $MSGL -l -d -o ret.dat
    assertEquals "0" "$?"
    insz=$(wc -c in.dat | awk '{print $1}')
    outsz=$(wc -c out.dat | awk '{print $1}')
    retsz=$(wc -c ret.dat | awk '{print $1}')
    assertEquals "1000000" "$insz"
    assertEquals "1000016" "$outsz"
    assertEquals "$insz" "$retsz"
    diff in.dat ret.dat
    assertEquals "0" "$?"
}

test_wrap_chunks_large() {
    echo MSGL=$MSGL
    cat /dev/urandom | head -c 1000000 > in.dat
    cat in.dat | $MSGL -l -p msgd -o out.dat
    assertEquals "0" "$?"
    cat out.dat | $MSGL -l -d -o ret.dat
    assertEquals "0" "$?"
    insz=$(wc -c in.dat | awk '{print $1}')
    outsz=$(wc -c out.dat | awk '{print $1}')
    retsz=$(wc -c ret.dat | awk '{print $1}')
    assertEquals "1000000" "$insz"
    #assertEquals "1000016" "$outsz"
    assertEquals "$insz" "$retsz"
    diff in.dat ret.dat
    assertEquals "0" "$?"
}

test_wrap_chunks_extract1() {
    echo MSGL=$MSGL
    (cat /dev/urandom | head -c 1000; sleep 1; cat /dev/urandom | head -c 1000; ) | tee in.dat |\
       $MSGL -l -p msgd -o out.dat
    assertEquals "0" "$?"
    cat out.dat | $MSGL -l -n 1 -d -o ret.dat
    assertEquals "0" "$?"
    insz=$(wc -c in.dat | awk '{print $1}')
    outsz=$(wc -c out.dat | awk '{print $1}')
    retsz=$(wc -c ret.dat | awk '{print $1}')
    assertEquals "2000" "$insz"
    assertEquals "1000" "$retsz"
    head -c $retsz in.dat > chck.dat
    diff chck.dat ret.dat
    assertEquals "0" "$?"
}

test_cleanup() {
    rm -f in.dat out.dat ret.dat chck.dat
}

. shunit2
