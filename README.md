# Just a Sample Testing Directory for CCExtractor

- See `scripts/` to know how tests are conducted
- What's being tested?
    1. `tests/isdb/0` : https://drive.google.com/file/d/0B_61ywKPmI0TMzlwZGw0MzdIc0U/view?usp=drive_link&resourcekey=0-UkWAUJcBIl_6uJL3nzCTcA
    2. `tests/isdb/1` : https://drive.google.com/file/d/0B_61ywKPmI0TM3dKRlJ6UjI0STQ/view?usp=drive_link&resourcekey=0-zwyV8fkI_xMeM3_1zUZ_RQ
    3. `tests/xds/0` : https://sampleplatform.ccextractor.org/sample/b22260d065ab537899baaf34e78a5184671f4bcb2df0414d05e6345adfd7812f
    4. `tests/xds/1` : https://sampleplatform.ccextractor.org/sample/97
- In each of `tests/isdb,xds/0,1` :
    1. `master_op` has output from [`ccextractor`](https://github.com/CCExtractor/ccextractor)'s `master` as of commit `dd2931153e594a2029e70c341516f2dd5720e047` on `feb 8, 2026`

    2. `new_op` has output from
         - currently [pr2109](https://github.com/CCExtractor/ccextractor/pull/2109) for the isdb samples
         - currently [pr2088](https://github.com/CCExtractor/ccextractor/pull/2109) for the xds samples