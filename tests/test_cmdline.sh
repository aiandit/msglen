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

. shunit2
