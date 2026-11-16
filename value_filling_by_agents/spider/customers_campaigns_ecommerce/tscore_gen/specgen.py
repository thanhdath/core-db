"""Specification-driven instance construction implemented by construction in Python."""
import datetime as dt
import re

_BASE_LO = dt.datetime(2008, 1, 1)
_BASE_HI = dt.datetime(2018, 3, 31, 23, 59, 59)
TXT = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ '
_STR = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

PLANTED_NULLS: dict = {}


def _rand_dt(rng, lo=_BASE_LO, hi=_BASE_HI):
    span = int((hi - lo).total_seconds())
    return (lo + dt.timedelta(seconds=rng.randint(0, max(0, span)))).strftime('%Y-%m-%d %H:%M:%S')


def _rand_after(rng, base_s):
    """A datetime string >= base_s inside the base window (or base_s + 1..N days when base is late)."""
    try:
        b = dt.datetime.strptime(str(base_s)[:19], '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return _rand_dt(rng)
    if b >= _BASE_HI:
        return (b + dt.timedelta(seconds=rng.randint(0, 86400))).strftime('%Y-%m-%d %H:%M:%S')
    hi = _BASE_HI
    return _rand_dt(rng, b, hi if hi > b else b + dt.timedelta(days=1))


def _rand_text(rng, lo=3, hi=12):
    return ''.join(rng.choice(TXT) for _ in range(rng.randint(lo, hi))).strip() or 'x'


def _rand_addr(rng):
    return '%d %s %s' % (rng.randint(1, 99999), rng.choice(['Street', 'Lane', 'Avenue', 'Road', 'Court']),
                         ''.join(rng.choice(TXT) for _ in range(rng.randint(4, 10))).strip())


def _rand_phone(rng):
    return '(%03d)%03d-%04d' % (rng.randint(200, 999), rng.randint(200, 999), rng.randint(0, 9999))


def _rand_email(rng):
    return '%s.%s@example.%s' % (_rand_text(rng, 4, 8).lower().replace(' ', ''),
                                 _rand_text(rng, 4, 8).lower().replace(' ', ''),
                                 rng.choice(['com', 'net', 'org']))


def _rand_pw(rng):
    return ''.join(rng.choice('0123456789abcdef') for _ in range(10))


def _rand_money(rng, lo=1.0, hi=100.0):
    return '%.2f' % rng.uniform(lo, hi)


def _groups(n):
    """Split n rows into groups of sizes 1, 2 and >=3 (used for GROUP columns)."""
    sizes, left = [], n
    if left >= 6:
        big = max(3, min(left - 3, 3 + left // 3))
        sizes = [1, 2, big]
        left -= 1 + 2 + big
        while left > 0:
            k = min(left, 4)
            sizes.append(k)
            left -= k
    elif left == 5:
        sizes = [1, 2, 2]
    elif left == 4:
        sizes = [1, 1, 2]
    elif left == 3:
        sizes = [1, 2]
    elif left == 2:
        sizes = [2]
    else:
        sizes = [max(1, left)]
    return sizes


def _fresh_int_keys(rng, n, taken):
    """n distinct positive integers not in `taken` (sequential-ish, fresh against compact PKs/UNIQUEs)."""
    out = []
    start = 1
    while len(out) < n:
        v = start
        start += 1
        if v in taken:
            continue
        out.append(v)
    return out


def _exceptions(spec):
    out = {}
    for e in spec.get('per_column_exceptions', []):
        out.setdefault((e.get('table'), e.get('column')), []).append(e)
    return out


def merge_spec_pools(pool: dict, spec: dict, schema) -> None:
    """Add enum / boundary targets to the routed literal pool (as observed values)."""
    for e in spec.get('per_column_exceptions', []):
        t, c = e.get('table'), e.get('column')
        if not t or not c:
            continue
        for v in e.get('targets', []) or []:
            if not isinstance(v, str):
                continue
            if re.fullmatch(r'\d', v):
                continue
            pool.setdefault((t, c), []).append(v)


def _spec_sizes(spec, rng):
    """Per-table row counts: spec value + small variation (0-230 cap, level x4 cap 2500)."""
    base = spec.get('table_sizes_per_instance') or {}
    sizes = {}
    for t, n in base.items():
        try:
            n = int(n)
        except (TypeError, ValueError):
            n = 0
        if n == 0:
            sizes[t] = 0
            continue
        jitter = rng.choice([0, 0, -1, 1, 2])
        sizes[t] = max(1, min(230, n + jitter))
    return sizes


def build_spec_instance(schema, pool: dict, spec: dict, rng, base_db: str = None):
    """Build one instance (dict table -> {column: [values]}) following the specification."""
    PLANTED_NULLS.clear()
    exc = _exceptions(spec)
    sizes = _spec_sizes(spec, rng)
    obs = schema.original_values
    inst: dict = {}

    def ex(t, c):
        return exc.get((t, c), [])

    def enum_vals(t, c):
        vals = []
        for e in ex(t, c):
            if e.get('pattern') == 'enum':
                vals += [str(v) for v in e.get('targets', []) if not re.fullmatch(r'\d(,.*)?', str(v))]
        vals += [str(v) for v in pool.get((t, c), []) if v not in vals]
        return vals or [str(v) for v in obs.get((t, c), []) if v is not None] or ['x']

    def boundary_vals(t, c):
        """Exact comparison-boundary literals plus one case variant (only for widened domains)."""
        vals = []
        for e in ex(t, c):
            if e.get('pattern') == 'comparison_boundary':
                for v in e.get('targets', []) or []:
                    v = str(v)
                    vals.append(v)
                    if v.lower() != v:
                        vals.append(v.lower())
                    elif v.upper() != v:
                        vals.append(v.upper())
        out = []
        for v in vals:
            if v not in out:
                out.append(v)
        return out

    def null_count(t, c, n, nullable):
        if not nullable or n <= 0:
            return 0
        ov = [v for v in obs.get((t, c), [])]
        share = (sum(1 for v in ov if v is None) / float(len(ov))) if ov else 0.0
        k = int(round(share * n))
        return max(1, min(n - 1 if n > 1 else n, k))

    def plant_nulls(vals, t, c, nullable):
        """Plant NULLs and record their positions in PLANTED_NULLS so the writer persists them."""
        n = len(vals)
        k = null_count(t, c, n, nullable)
        if k <= 0:
            return vals
        idx = list(range(n))
        rng.shuffle(idx)
        chosen = set(idx[:k])
        for i in chosen:
            vals[i] = None
        PLANTED_NULLS.setdefault((t, c), set()).update(chosen)
        return vals

    def compact_pk(t, c):
        return {v for v in obs.get((t, c), []) if isinstance(v, int)}

    def taken_keys(t):
        """Full taken-set for a table's integer PK: compact PK values (coerced) + UNIQUE column values."""
        tm = schema.tables.get(t)
        taken = set()
        if tm is None:
            return taken
        for c in tm.columns:
            if c.name in tm.primary_key or c.unique:
                for v in obs.get((t, c.name), []):
                    if v is None:
                        continue
                    try:
                        taken.add(int(v))
                    except (TypeError, ValueError):
                        pass
        return taken

    nP = sizes.get('Premises', 0)
    ptype = enum_vals('Premises', 'premises_type') or ['Residence']
    ptyp = [rng.choice(ptype) for _ in range(nP)]
    pdet = []
    for i in range(nP):
        ov = [v for v in obs.get(('Premises', 'premise_details'), []) if v is not None]
        pdet.append((str(rng.choice(ov)) + ' ' + _rand_text(rng, 2, 4)) if ov and rng.random() < 0.5 else _rand_addr(rng))
    pdet = plant_nulls(pdet, 'Premises', 'premise_details', True)
    pref = _fresh_int_keys(rng, nP, taken_keys('Premises'))
    inst['Premises'] = {'premise_id': list(pref), 'premises_type': ptyp, 'premise_details': pdet}

    nPr = sizes.get('Products', 0)
    pcats = enum_vals('Products', 'product_category') or ['Food']
    pcat = [rng.choice(pcats) for _ in range(nPr)]
    pname = []
    for i in range(nPr):
        ov = [str(v) for v in obs.get(('Products', 'product_name'), []) if v is not None]
        pname.append((rng.choice(ov) + ' ' + rng.choice(_STR)) if ov and rng.random() < 0.6 else _rand_text(rng, 4, 12))
    pname = plant_nulls(pname, 'Products', 'product_name', True)
    prodref = _fresh_int_keys(rng, nPr, taken_keys('Products'))
    inst['Products'] = {'product_id': list(prodref), 'product_category': pcat, 'product_name': pname}

    nC = sizes.get('Customers', 0)
    pmeth = enum_vals('Customers', 'payment_method') or ['Credit Card']
    pm = [rng.choice(pmeth) for _ in range(nC)]
    ovn = [str(v) for v in obs.get(('Customers', 'customer_name'), []) if v is not None] or ['Anna', 'Ben', 'Cara']
    names = []
    for g in _groups(nC):
        base = rng.choice(ovn)
        for _ in range(g):
            if g >= 3:
                names.append(base if rng.random() < 0.9 else (_rand_text(rng, 5, 9).title()))
            else:
                names.append(base if rng.random() < 0.5 else (_rand_text(rng, 5, 9).title()))
    if not names:
        names = [_rand_text(rng, 5, 9).title() for _ in range(nC)]
    dup_target = rng.uniform(0.20, 0.50)
    for i in range(len(names)):
        if i > 0 and rng.random() < dup_target:
            names[i] = rng.choice(names[:i])
    names = names[:nC]
    phone = [_rand_phone(rng) for _ in range(nC)]
    email = [_rand_email(rng) for _ in range(nC)]
    addr = [_rand_addr(rng) for _ in range(nC)]
    login = [None] * nC
    if nC > 0:
        PLANTED_NULLS.setdefault(('Customers', 'customer_login'), set()).update(range(nC))
    pw = [_rand_pw(rng) for _ in range(nC)]
    for col, vals in (('customer_name', names), ('customer_phone', phone),
                      ('customer_email', email), ('customer_address', addr),
                      ('customer_password', pw)):
        vals = plant_nulls(vals, 'Customers', col, True)
        inst.setdefault('Customers', {})[col] = vals
    inst['Customers']['payment_method'] = pm
    inst['Customers']['customer_login'] = login
    custref = _fresh_int_keys(rng, nC, taken_keys('Customers'))
    inst['Customers']['customer_id'] = list(custref)

    nM = sizes.get('Mailshot_Campaigns', 0)
    scats = enum_vals('Mailshot_Campaigns', 'product_category') or ['food']
    msname_pool = [str(v) for v in pool.get(('Mailshot_Campaigns', 'mailshot_name'), [])] or ['US', 'FED', 'USPS', 'AL']
    msname_pool += [str(v) for v in obs.get(('Mailshot_Campaigns', 'mailshot_name'), []) if v is not None]
    msname = [rng.choice(msname_pool) for _ in range(nM)]
    mstart = [_rand_dt(rng, _BASE_LO, dt.datetime(2017, 12, 31)) for _ in range(nM)]
    mend = [_rand_after(rng, s) for s in mstart]
    inst['Mailshot_Campaigns'] = {
        'mailshot_id': _fresh_int_keys(rng, nM, taken_keys('Mailshot_Campaigns')),
        'product_category': [rng.choice(scats) for _ in range(nM)],
        'mailshot_name': plant_nulls(msname, 'Mailshot_Campaigns', 'mailshot_name', True),
        'mailshot_start_date': plant_nulls(mstart, 'Mailshot_Campaigns', 'mailshot_start_date', True),
        'mailshot_end_date': mend,
    }
    for i in range(nM):
        s, e = inst['Mailshot_Campaigns']['mailshot_start_date'][i], mend[i]
        if s is not None and e is not None and e < s:
            inst['Mailshot_Campaigns']['mailshot_end_date'][i] = _rand_after(rng, s)

    nA = sizes.get('Customer_Addresses', 0)
    type_pool = enum_vals('Customer_Addresses', 'address_type_code') or ['Billing', 'Shipping']
    ca_c = [rng.choice(custref) for _ in range(nA)] if custref else []
    ca_p = [rng.choice(pref) for _ in range(nA)] if pref else []
    ca_from = [_rand_dt(rng) for _ in range(nA)]
    ca_to = [_rand_after(rng, s) for s in ca_from]
    ca_type = [rng.choice(type_pool) for _ in range(nA)]
    if pref and nA > 0:
        used = set(ca_p)
        spare = [p for p in pref if p not in used]
        if not spare:
            victim = rng.randrange(len(ca_p))
            replacement = rng.choice([p for p in pref if p != ca_p[victim]] or pref)
            ca_p[victim] = replacement
    ca_to = plant_nulls(ca_to, 'Customer_Addresses', 'date_address_to', True)
    inst['Customer_Addresses'] = {'customer_id': ca_c, 'premise_id': ca_p, 'date_address_from': ca_from,
                                  'address_type_code': ca_type, 'date_address_to': ca_to}

    nO = sizes.get('Customer_Orders', 0)
    stat_pool = enum_vals('Customer_Orders', 'order_status_code') or ['Cancelled', 'Delivered', 'Paid']
    ship_pool = enum_vals('Customer_Orders', 'shipping_method_code') or ['Unspecified', 'FedEx', 'UPS']
    stat_b = boundary_vals('Customer_Orders', 'order_status_code') or ['Paid']
    ship_b = boundary_vals('Customer_Orders', 'shipping_method_code') or ['FedEx']
    co_c = [rng.choice(custref) for _ in range(nO)] if custref else []
    co_stat, co_ship = [], []
    for _ in range(nO):
        u = rng.random()
        co_stat.append(rng.choice(stat_b) if u < 0.35 and stat_b else rng.choice(stat_pool))
        co_ship.append(rng.choice(ship_b) if u < 0.25 and ship_b else rng.choice(ship_pool))
    if nO >= 2:
        co_stat[0], co_ship[0] = 'Paid', 'FedEx'
        co_stat[1], co_ship[1] = 'paid', 'fedex'
    placed = [_rand_dt(rng, _BASE_LO, dt.datetime(2017, 6, 30)) for _ in range(nO)]
    delivered = []
    for s in placed:
        delivered.append(_rand_after(rng, s) if rng.random() < 0.85 else None)
    charges = ['%.2f' % max(0.0, float(_rand_money(rng))) for _ in range(nO)]
    charges = plant_nulls(charges, 'Customer_Orders', 'order_shipping_charges', True)
    if nO > 0 and all(c is not None for c in charges):
        charges[rng.randrange(nO)] = None
        PLANTED_NULLS.setdefault(('Customer_Orders', 'order_shipping_charges'), set()).add(
            next(i for i, c in enumerate(charges) if c is None))
    inst['Customer_Orders'] = {
        'order_id': _fresh_int_keys(rng, nO, taken_keys('Customer_Orders')),
        'customer_id': co_c, 'order_status_code': co_stat, 'shipping_method_code': co_ship,
        'order_placed_datetime': placed, 'order_delivered_datetime': delivered,
        'order_shipping_charges': charges,
    }

    nMC = sizes.get('Mailshot_Customers', 0)
    oc_enum = ['Order', 'No Response']
    oc_b = boundary_vals('Mailshot_Customers', 'outcome_code') or ['No Response', 'Order']
    mc_mid = [rng.choice(inst['Mailshot_Campaigns']['mailshot_id']) for _ in range(nMC)] if nM else []
    mc_cid = []
    free_customers = list(custref)
    for g in _groups(nMC):
        if free_customers and rng.random() < 0.7:
            c = free_customers.pop(rng.randrange(len(free_customers)))
        else:
            c = rng.choice(custref) if custref else 1
        mc_cid.extend([c] * g)
    mc_cid = mc_cid[:nMC]
    oc = []
    for i in range(nMC):
        if i < 2:
            oc.append('Order')
        else:
            oc.append(rng.choice(oc_b) if rng.random() < 0.6 else rng.choice(oc_enum))
    if nMC >= 2:
        oc[0], oc[1] = 'Order', 'No Response'
    if nMC >= 4:
        oc[2], oc[3] = 'order', 'no response'
    if custref:
        seen_cust = {}
        for c, o in zip(mc_cid, oc):
            seen_cust.setdefault(c, []).append(o)
        ok = any({x.lower() for x in v} >= {'order', 'no response'} for v in seen_cust.values())
        if not ok and nMC >= 2:
            mc_cid[0] = mc_cid[1] = mc_cid[0] if mc_cid else 1
            oc[0], oc[1] = 'Order', 'No Response'
    mdate = [_rand_dt(rng, dt.datetime(2018, 1, 1), _BASE_HI) for _ in range(nMC)]
    mdate = plant_nulls(mdate, 'Mailshot_Customers', 'mailshot_customer_date', True)
    inst['Mailshot_Customers'] = {'mailshot_id': mc_mid, 'customer_id': mc_cid, 'outcome_code': oc,
                                  'mailshot_customer_date': mdate}

    nI = sizes.get('Order_Items', 0)
    istat_pool = enum_vals('Order_Items', 'order_item_status_code') or ['Delivered', 'Paid', 'Cancelled']
    isc = enum_vals('Order_Items', 'item_status_code') or ['good']
    orders = inst['Customer_Orders']
    oids = orders['order_id']
    placed_by_order = dict(zip(oids, orders['order_placed_datetime']))
    oi_oid = [rng.choice(oids) for _ in range(nI)] if oids else []
    oi_pid = [rng.choice(inst['Products']['product_id']) for _ in range(nI)] if nPr else []
    stat = [rng.choice(istat_pool) for _ in range(nI)]
    istd = [rng.choice(isc) for _ in range(nI)]
    qty = [str(rng.randint(1, 9)) for _ in range(nI)]
    idd = []
    for oid in oi_oid:
        base = placed_by_order.get(oid)
        if base is not None and rng.random() < 0.85:
            idd.append(_rand_after(rng, base))
        else:
            idd.append(_rand_dt(rng, dt.datetime(2018, 2, 1), _BASE_HI) if rng.random() < 0.5 else None)
    istd = plant_nulls(istd, 'Order_Items', 'item_status_code', True)
    idd = plant_nulls(idd, 'Order_Items', 'item_delivered_datetime', True)
    qty = plant_nulls(qty, 'Order_Items', 'item_order_quantity', True)
    qty = [q if q is None else str(max(1, int(q))) for q in qty]
    inst['Order_Items'] = {
        'item_id': _fresh_int_keys(rng, nI, taken_keys('Order_Items')),
        'order_item_status_code': stat, 'order_id': oi_oid, 'product_id': oi_pid,
        'item_status_code': istd, 'item_delivered_datetime': idd, 'item_order_quantity': qty,
    }

    return inst, sizes


def load_spec(path: str = None) -> dict:
    """Re-export of cli._load_spec-like loader (kept here so specgen can be used stand-alone)."""
    import json
    import os
    if not path:
        cand = os.path.join(os.path.dirname(__file__), 'specification.json')
        path = cand if os.path.exists(cand) else None
    if not path:
        return {}
    try:
        with open(path) as f:
            return json.load(f) or {}
    except Exception:
        return {}
