#
# ++ @  @ ++  ++++++++
#  ++    ++   ++
#   ++  ++    ++  ++++
#    ++++     ++     +
#     ++      ++++++++
#
#
#   LOW LEVEL & SIMPLE & LIGHTWEIGHT
#
#   E-mail : nz2324@126.com
#
#   URL : http://hit9.org
#
#   Licence : BSD
#
#   API : doc/API.md
#
# Permission to use, copy, modify,
# and distribute this software for any purpose with
# or without fee is hereby granted,
# provided that the above copyright notice
# and this permission notice appear in all copies.
#

import re
import MySQLdb
import MySQLdb.cursors

# regular expression to get matched rows number from cursor's info
RowsMatchedRE = re.compile(r'Rows matched: (\d+)')


# type marks for CURD

Q_INSERT = 1
Q_UPDATE = 2
Q_SELECT = 3
Q_DELETE = 4


# type marks for runtimes

QR_WHERE = 1
QR_SET = 2
QR_ORDERBY = 3
QR_SELECT = 4
QR_TABLES = 5


class Database:

    """class to manage database connection"""

    # api:
    # return func
    # None Database.config(**configs)
    # cursor Database.execute(SQLstring)
    # int Database.query_times

    configs = {  # default configs
        "host": "localhost",
        "port": 3306,  # int
        "db": "",  # required
        "user": "",  # required
        "passwd": "",  # required
        "charset": "utf8"
    }
    conn = None  # connection object for MySQLdb

    debug = True  # debug as default

    query_times = 0

    SQL = None  # SQL last time executed

    @classmethod
    def config(cls, debug=True, **configs):
        cls.configs.update(configs)
        cls.debug = debug

    @classmethod
    def connect(cls):
        # if not connected, new one, else use the exist
        if not cls.conn or not cls.conn.open:
            cls.conn = MySQLdb.connect(
                cursorclass=MySQLdb.cursors.DictCursor,
                **cls.configs
            )
        return cls.conn

    @classmethod
    def execute(cls, SQL):
        cursor = Database.connect().cursor()
        try:
            cursor.execute(SQL)
        except Exception, e:
            if cls.debug:
                print "SQL :", SQL  # print SQL
                raise e
        cls.query_times = cls.query_times+1
        cls.SQL = SQL
        # add attribute 're' to cursor:store query matched rows number
        cursor.re = int(
            RowsMatchedRE.search(cursor._info).group(1)
        ) if cursor._info else int(cursor.rowcount)
        return cursor


class Leaf(object):

    def _expr(op):
        def _e(self, r):
            return Expr(left=self, right=r, op=op)
        return _e

    __lt__ = _expr(" < ")

    __le__ = _expr(" <= ")

    __gt__ = _expr(" > ")

    __ge__ = _expr(" >= ")

    __ne__ = _expr(" <> ")

    __eq__ = _expr(" = ")

    __add__ = _expr(" + ")

    __and__ = _expr(" and ")

    __or__ = _expr(" or ")


class Expr(Leaf):

    def __init__(self, left, right, op):
        self.left = left
        self.right = right
        self.op = op

        self.exprstr = None  # record exprstr

    @property
    def _tostr(self):  # singleton get exprstr, set exprstr when needed
        if not self.exprstr:
            self.exprstr = self._str(self.left)+self.op+self._str(self.right)
        return self.exprstr

    def _str(self, side):  # turn some side to str in SQL
        if isinstance(side, Field):
            return side.fullname
        elif isinstance(side, Expr):
            return side._tostr
        else:
            return "'"+MySQLdb.escape_string(str(side))+"'"   # escape_string


class EqExpr(Expr):  # eq expr
    #
    # api:
    # (fieldname, valuestring) eqexpr._toitem
    #

    def __init__(self, left, right):
        super(EqExpr, self).__init__(left, right, " = ")

    @property
    def _toitem(self):   # User.name == "name" => ("name", "name")
        return (self.left.name, str(self.right))


class FieldDescriptor(object):  # descriptor for Field objs

    def __init__(self, field):
        self.name = field.name
        self.field = field

    def __get__(self, instance, type=None):
        if instance:  # return data
            return instance._data[self.name]
        return self.field  # Model.field_name will return Field instance

    def __set__(self, instance, value):
        instance._data[self.name] = value


class Field(Leaf):  # Field Class

    def __init__(self):

        self.primarykey = False  # default: Field instance not a primarykey

    def describe(self, name, model):  # describe attr by FieldDescriptor
        self.name = name
        self.model = model
        self.fullname = self.model.table_name+"."+self.name
        setattr(model, name, FieldDescriptor(self))  # add Descriptor

    def __eq__(self, r):  # overload Leaf __eq__.return  EqExpr instance
        return EqExpr(left=self, right=r)


class PrimaryKey(Field):

    def __init__(self):
        self.primarykey = True


class SelectResult(object):  # wrap select result

    def __init__(self, model):
        self.model = model
        self.cursor = None
        self.flst = None

    @property
    def nfdct(self):  # result data dict key <=> field instance pairs dict
        dct = {}
        for f in self.flst:
            if f.name not in dct:
                dct[f.name] = f
            else:
                dct[f.fullname] = f
        return dct

    def mddct(self, dct, nfdct):  # model data_dict pasirs dict
        mlst = self.model.models
        b = dict((m, {}) for m in mlst)
        for k, v in dct.iteritems():
            field = nfdct[k]
            data_dct = b[field.model]
            data_dct[field.name] = v
        return b

    def fetchone(self):  # fetchone a time
        dct = self.cursor.fetchone()
        self.cursor.close()

        if self.model.single:
            return self.model(**dct) if dct else None
        else:
            nfdct = self.nfdct
            b = self.mddct(dct, nfdct)
            return tuple(m(**b[m]) for m in self.model.models)

    def fetchall(self):  # fetchall result

        data = self.cursor.fetchall()
        self.cursor.close()

        if self.model.single:
            for dct in data:
                yield self.model(**dct)
        else:
            nfdct = self.nfdct

            for dct in data:
                b = self.mddct(dct, nfdct)
                yield tuple(m(**(b[m])) for m in self.model.models)

    @property
    def count(self):
        return int(self.cursor.rowcount)  # cast to int


class Query(object):  # Runtime Query

    def __init__(self, model=None):

        self.model = model
        self.runtime = (   # infomation in single query, each's type:list
            "_where",      # expr list
            "_set",        # eqexpr list
            "_orderby",    # [field, desc(bool)]
            "_select"     # fields to select.type:list
        )
        self.reset_runtime()  # reset, to init runtime as attrs
        self.select_result = SelectResult(model)  # store select result

    def reset_runtime(self):
        self.__dict__.update({}.fromkeys(self.runtime, []))

    def set_orderby(self, t):  # t: (Field instance, True of False)
        self._orderby = list(t)

    def set_select(self, flst):  # flst:  Field instance list
        primarykey = self.model.primarykey
        flst = list(flst)
        if flst:  # if no field figured out, select all as default
            if self.model.single:
                flst.append(primarykey)  # add primarykey to select
            else:
                flst.extend(primarykey)
            flst = list(set(flst))  # remove duplicates
        else:
            flst = self.model.get_field_lst()
        self._select = self.select_result.flst = flst

    def set_where(self, lst, dct):
        lst = list(lst)  # cast to list
        if self.model.single:  # single model
            fields = self.model.fields
            lst.extend([fields[k] == v for k, v in dct.iteritems()])
        self._where = lst

    def set_set(self, lst, dct):
        lst = list(lst)
        if self.model.single:
            fields = self.model.fields
            primarykey = self.model.primarykey
            lst.extend(
                [fields[k] == v
                    for k, v in dct.iteritems() if fields[k] is not primarykey]
            )
        self._set = lst

    # generate function for get str of runtimes
    def _G(type=None):
        @property
        def g(self):

            dct = {
                QR_WHERE: self._where,
                QR_SELECT: self._select,
                QR_SET: self._set,
                QR_ORDERBY: self._orderby,
            }

            lst = dct[type]

            if not lst:
                return ""

            if type is QR_WHERE:
                return " where "+" and ".join([expr._tostr for expr in lst])

            elif type is QR_SELECT:
                return ", ".join([field.fullname for field in lst])

            elif type is QR_SET:
                return " set " + ", ".join([expr._tostr for expr in lst])

            elif type is QR_ORDERBY:
                orderby_str = " order by "+lst[0].fullname
                if lst[1]:
                    orderby_str = orderby_str+" desc "
                return orderby_str
        return g

    get_orderby = _G(QR_ORDERBY)

    get_select = _G(QR_SELECT)

    get_set = _G(QR_SET)

    get_where = _G(QR_WHERE)

    def makeSQL(self, type, model=None):

        table = self.model.table_name

        if model is None:
            model = self.model

        _table = model.table_name

        if type is Q_INSERT:
            SQL = "insert into " + table + " " + self.get_set
        elif type is Q_UPDATE:
            SQL = "update " + table+" " + self.get_set + self.get_where
        elif type is Q_SELECT:
            SQL = (
                "select " + self.get_select + " from " + table +
                self.get_where + self.get_orderby
            )
        elif type is Q_DELETE:
            SQL = (
                "delete " + _table + " from " + table + self.get_where
            )
        return SQL

    def _Q(type):   # function generator for CURD
        def func(self, model=None):

            if type is Q_DELETE and model:
                SQL = self.makeSQL(Q_DELETE, model)
            else:
                SQL = self.makeSQL(type)

            cursor = Database.execute(SQL)

            re = None

            if type in (Q_UPDATE, Q_DELETE):  # return 0 or 1
                re = cursor.re
            elif type is Q_INSERT:  # return lastrowid
                re = cursor.lastrowid if cursor.re else None
            elif type is Q_SELECT:
                # reset select_result's cursor
                self.select_result.cursor = cursor
                re = self.select_result
            if type is not Q_SELECT:
                cursor.close()
            self.reset_runtime()
            return re
        return func

    #generate CURD Functions

    insert = _Q(Q_INSERT)

    update = _Q(Q_UPDATE)

    select = _Q(Q_SELECT)

    delete = _Q(Q_DELETE)


class MetaModel(type):  # metaclass for 'single Model' Class

    def __init__(cls, name, bases, attrs):

        cls.table_name = cls.__name__.lower()

        fields = {}  # name <=> fields pairs
        primarykey = None

        for name, attr in cls.__dict__.iteritems():
            if isinstance(attr, Field):
                attr.describe(name, cls)  # describe attr
                fields[name] = attr
                if attr.primarykey:
                    primarykey = attr

        if primarykey is None:  # default primarykey => 'id'
            primarykey = PrimaryKey()
            primarykey.describe('id', cls)
            fields['id'] = primarykey

        cls.fields = fields
        cls.primarykey = primarykey
        cls.query = Query(cls)  # instance a Query for Model cls

    def __and__(self, m):
        if m.single:
            return JoinModel(self, m)
        else:
            m.models.insert(0, self)
            return m

    def __contains__(self, obj):
        if isinstance(obj, self) and self.where(**obj.data).select().count:
            return True
        return False


class Model(object):

    __metaclass__ = MetaModel
    single = True  # if Single

    def __init__(self, *lst, **dct):
        self._data = {}
        # update _data by expr lst
        self._data.update(dict(x._toitem for x in lst))
        self._data.update(dct)
        self._cache = self._data.copy()

    @property
    def data(self):
        return self._data

    @property
    def _id(self):
        return self._data.setdefault(self.primarykey.name, None)

    @classmethod
    def get_field_lst(cls):
        return cls.fields.values()

    def set_id(self, _id):
        self._data[self.primarykey.name] = _id

    def save(self):
        model = self.__class__
        if not self._id:  # insert one record
            model.query.set_set([], self._data)
            id = model.query.insert()
            if id:
                self.set_id(id)
                self._cache = self._data.copy()  # sync cache after save
                return id
        else:
            # only update changed data
            dct = dict(set(self._data.items()) - set(self._cache.items()))
            if not dct:
                return 1  # data not change
            re = model.at(self._id).update(**dct)
            if re:
                self._cache = self._data.copy()  # sync cache after save
                return re  # success update
        return 0

    def destroy(self):
        if self._id:
            model = self.__class__
            return model.at(self._id).delete()
        return 0

    @classmethod
    def select(cls, *flst):
        cls.query.set_select(flst)
        return cls.query.select()

    @classmethod
    def create(cls, *lst, **dct):
        cls.query.set_set(lst, dct)
        id = cls.query.insert()
        if id:
            dct[cls.primarykey.name] = id  # add id to dct
            return cls(*lst, **dct)
        return None

    @classmethod
    def delete(cls):
        return cls.query.delete()

    @classmethod
    def update(cls, *lst, **dct):
        cls.query.set_set(lst, dct)
        return cls.query.update()

    @classmethod
    def where(cls, *lst, **dct):
        cls.query.set_where(lst, dct)
        return cls

    @classmethod
    def at(cls, _id):  # find by id
        cls.where(cls.primarykey == _id)
        return cls

    @classmethod
    def orderby(cls, field, desc=False):
        cls.query.set_orderby((field, desc))
        return cls


class JoinModel(object):

    def __init__(self, *models):
        self.models = list(models)  # cast to list
        self.single = False
        self.query = Query(self)

    def __and__(self, m):
        if m.single:  # if single, append to models
            self.models.append(m)
        else:
            self.models.extend(m.models)
        return self

    @property
    def table_name(self):
        return ", ".join([m.table_name for m in self.models])

    @property
    def primarykey(self):
        return [m.primarykey for m in self.models]

    def get_field_lst(self):
        fls = []
        lst = [m.get_field_lst() for m in self.models]
        return sum(lst, [])

    def where(self, *lst):
        self.query.set_where(lst, {})
        return self

    def select(self, *lst):
        self.query.set_select(lst)
        return self.query.select()

    def update(self, *lst):
        self.query.set_set(lst, {})
        return self.query.update()

    def delete(self, model=None):  # model or joinmodel
        if not model:
            model = self
        return self.query.delete(model)

    def orderby(self, field, desc=False):
        self.query.set_orderby((field, desc))
        return self
