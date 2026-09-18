import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'money-machine'))
from mm_core import connect
d = connect()
row = d.execute('SELECT * FROM businesses WHERE id=3').fetchone()
print(dict(row) if row else 'NOT FOUND')
