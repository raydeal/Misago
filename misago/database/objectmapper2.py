# WIP: Experimental rewrite for object mapper
from dataclasses import dataclass, replace
from ntpath import join
from typing import Any, Dict, Iterable, List, Optional, Sequence, Type, Union

from sqlalchemy import asc, desc, func
from sqlalchemy.sql import ClauseElement, ColumnElement, TableClause, not_, select

from .database import database


class ObjectMapper:
    tables: Dict[str, TableClause]
    mappings: Dict[str, Union[Type, dict]]

    def __init__(self):
        self.tables = {}
        self.mappings = {}

    def set_mapping(self, table: TableClause, repr: Union[Type, dict]):
        self.tables[table.name] = table
        self.mappings[table.name] = repr

    def query_table(self, table: TableClause) -> "ObjectMapperQuery":
        state = ObjectMapperQueryState(table)
        return ObjectMapperRootQuery(self, state)


@dataclass
class ObjectMapperQueryState:
    table: TableClause
    filter: Optional[List[dict]] = None
    exclude: Optional[List[dict]] = None
    join: Optional[List[str]] = None
    join_root: Optional[TableClause] = None
    join_tables: Optional[Dict[str, TableClause]] = None
    order_by: Optional[Sequence[str]] = None
    offset: Optional[int] = None
    limit: Optional[int] = None


class ObjectMapperQuery:
    orm: ObjectMapper
    state: ObjectMapperQueryState

    def __init__(self, orm: ObjectMapper, state: ObjectMapperQueryState):
        self.orm = orm
        self.state = state

    def filter(self, *expressions, **conditions) -> "ObjectMapperQuery":
        filters = list(self.state.filter or [])
        if expressions:
            filters.extend(expressions)
        if conditions:
            filters.extend([conditions])
        new_state = replace(self.state, filter=filters)
        return ObjectMapperQuery(self.orm, new_state)

    def exclude(self, *expressions, **conditions) -> "ObjectMapperQuery":
        excludes = list(self.state.exclude or [])
        if expressions:
            excludes.extend(expressions)
        if conditions:
            validate_conditions(self.state, conditions)
            excludes.extend([conditions])
        new_state = replace(self.state, exclude=excludes)
        return ObjectMapperQuery(self.orm, new_state)

    def join_on(self, *columns: str) -> "ObjectMapperQuery":
        if not self.state.join_root:
            self.state = replace(self.state, join_root=self.state.table.alias("r"))

        new_join = self.state.join[:] if self.state.join else []
        new_join_tables = (
            self.state.join_tables.copy() if self.state.join_tables else {}
        )
        for join_on in columns:
            if "." in join_on:
                table = self.state.table
                join_path = []
                for join_col in join_on.split("."):
                    join_path.append(join_col)
                    validate_column(table, join_col)
                    foreign_key, *_ = table.c[join_col].foreign_keys
                    table = foreign_key.column.table
                    join_name = ".".join(join_path)
                    if join_name not in new_join_tables:
                        new_join_tables[join_name] = table.alias(
                            f"j{len(new_join_tables)}"
                        )
            elif join_on not in new_join_tables:
                validate_column(self.state.table, join_on)
                foreign_key, *_ = self.state.table.c[join_on].foreign_keys
                new_join_tables[join_on] = foreign_key.column.table.alias(
                    f"j{len(new_join_tables)}"
                )

            # Join validated column
            new_join.append(join_on)

        new_state = replace(self.state, join=new_join, join_tables=new_join_tables)
        return ObjectMapperQuery(self.orm, new_state)

    def _join_on_column_deep__(
        self, join_name: str, columns: Sequence[str]
    ) -> "ObjectMapperQuery":
        columns_len = len(columns) - 1
        new_join = self.state.join.copy() if self.state.join else {}
        new_join_order = list(self.state.join_order) if self.state.join_order else []
        table = self.state.table
        for i, column in enumerate(columns):
            if column not in table.c:
                raise InvalidColumnError(column, table)

            path.append(column)
            join_name = ".".join(path)
            if join_name in new_join:
                if not new_join[join_name].include_in_result:
                    # Include intermediate join col in resultset
                    new_join[join_name].include_in_result = True

                table = new_join[join_name].table
                continue

            column_obj = table.c[column]
            foreign_key, *_ = column_obj.foreign_keys
            join_table = foreign_key.column.table.alias(f"j{len(new_join)}")
            join_column = join_table.c[foreign_key.column.name]

            new_join[join_name] = ObjectMapperJoin(
                right_column=join_column,
                table=join_table,
                on_expression=table.c[column] == join_column,
                include_in_result=i + 1 == columns_len,
            )

            table = join_table

        new_join_order.append(join_name)
        new_state = replace(self.state, join=new_join, join_order=new_join_order)
        return ObjectMapperQuery(self.orm, new_state)

    def offset(self, offset: int) -> "ObjectMapperQuery":
        new_state = replace(self.state, offset=offset)
        return ObjectMapperQuery(self.orm, new_state)

    def limit(self, limit: int) -> "ObjectMapperQuery":
        new_state = replace(self.state, limit=limit)
        return ObjectMapperQuery(self.orm, new_state)

    def order_by(self, *columns: str) -> "ObjectMapperQuery":
        new_state = replace(self.state, order_by=columns)
        return ObjectMapperQuery(self.orm, new_state)

    async def update(self, values: dict):
        raise NotImplementedError("TODO")

    async def delete(self) -> int:
        query = self.state.table.delete()
        query = filter_query(self.state, query)
        await database.execute(query)

    async def delete_all(self) -> int:
        raise NotImplementedError(
            "'delete_all()' method is not available on filtered queries. "
            "To delete filtered objects call 'delete()'."
        )

    async def count(self) -> int:
        query = select([func.count()]).select_from(self.state.table)
        query = filter_query(self.state, query)
        query = slice_query(self.state, query)
        return await database.fetch_val(query)

    async def exists(self) -> bool:
        new_state = replace(
            self.state,
            limit=self.state.offset + 1 if self.state.offset else 1,
        )
        query = select([func.count()]).select_from(new_state.table)
        query = filter_query(new_state, query)
        query = slice_query(new_state, query)
        return bool(await database.fetch_val(query))

    async def all(self, *columns: str, named: bool = True) -> List[Any]:
        if not self.state.join:
            return await select_from_one_table(
                self.orm, self.state, columns, named=named
            )

        if columns:
            raise NotImplementedError("TODO!")

        return await select_from_joined_tables(self.orm, self.state)

    def _all_simple(self, rows: List[dict], columns: List[str], named: bool):
        if columns:
            if named:
                return [dict(**row) for row in rows]
            else:
                return [tuple(row.values()) for row in rows]

        if named:
            mapping = self.orm.mappings.get(self.state.table.element.name, dict)
            return [mapping(**row) for row in rows]
        else:
            return [tuple(row) for row in rows]

    def _all_with_joins(self, rows: List[dict], columns: List[str], named: bool):
        if columns:
            return rows  # rows are already mapped to cols in joined query

        # Map rows dicts to items
        ordered_joins = tuple(
            self.state.join[join_name] for join_name in self.state.join_order
        )

        mappings = [self.orm.mappings.get(self.state.table.element.name, dict)]
        for join in ordered_joins:
            if join.include_in_result:
                mappings.append(self.orm.mappings.get(join.table.element.name, dict))

        for i, row in enumerate(rows):
            rows[i] = (mapping(**row[m]) for m, mapping in enumerate(mappings))

        return rows

    async def one(self, *columns: str):
        new_state = replace(self.state, offset=None, limit=2)
        results = await select_rows(new_state, columns)
        raise NotImplemented("TODO!")


class ObjectMapperRootQuery(ObjectMapperQuery):
    async def insert(self, values: dict):
        table = self.state.table
        validate_columns(table, values.keys())

        query = table.insert(None).values(**values)
        new_row_id = await database.execute(query)
        if table.primary_key.columns is not None and new_row_id:
            values[table.primary_key.columns[0].name] = new_row_id

        mapping = self.orm.mappings.get(table.name, dict)
        return mapping(**values)

    async def bulk_insert(self, values: List[dict]):
        new_memberships = self.state.table.insert().values(values)
        await database.fetch_all(new_memberships)

    async def delete_all(self):
        await database.execute(self.state.table.delete())

    async def delete(self) -> int:
        raise NotImplementedError(
            "'delete()' method is not available on root queries. "
            "To delete all objects call 'delete_all()'."
        )


class MultipleObjectsReturned(RuntimeError):
    pass


class DoesNotExist(RuntimeError):
    pass


async def select_from_one_table(
    orm: ObjectMapper,
    state: ObjectMapperQueryState,
    columns: Sequence[str],
    *,
    named: bool = True,
) -> List[Any]:
    """Select all columns from simple select, return them as dict/tuple/mapping"""
    if columns:
        validate_columns(state.table, columns)
        query = select(state.table.c[col] for col in columns)
    else:
        query = state.table.select(None)

    query = filter_query(state, query)
    query = slice_query(state, query)
    query = order_query(state, query)

    rows = await database.fetch_all(query)

    if columns:
        if named:
            return [dict(**row) for row in rows]
        else:
            return [tuple(row.values()) for row in rows]

    mapping = orm.mappings.get(state.table.name)
    return [mapping(**row) for row in rows]


async def select_from_joined_tables(orm: ObjectMapper, state: ObjectMapperQueryState):
    tables = 1
    root = state.join_root

    cols = tuple(root.c.values())
    cols_mappings = tuple((0, c.name) for c in cols)

    # Build query FROM ... LEFT JOIN ...
    query_from = root
    for join_on, join_table in state.join_tables.items():
        if "." in join_on:
            left_table_name, join_on = join_on.rsplit(".", 1)
            left_table = state.join_tables[left_table_name]
        else:
            left_table = root

        join_left = left_table.c[join_on]
        foreign_key, *_ = join_left.foreign_keys
        join_column = join_table.c[foreign_key.column.name]
        query_from = query_from.outerjoin(join_table, join_left == join_column)

    # Build SELECT ...
    for join_name in state.join:
        join_table = state.join_tables[join_name]
        cols += tuple(c.label(f"t{tables}_{c.name}") for c in join_table.c.values())
        cols_mappings += tuple((tables, c.name) for c in join_table.c.values())
        tables += 1

    query = select(cols).select_from(query_from)

    query = filter_query(state, query, in_join=True)
    query = slice_query(state, query)
    query = order_query(state, query, in_join=True)

    # Tables keys and mappings
    keys = (root.primary_key[0].name,) + tuple(
        state.join_tables[join_name].primary_key[0].name for join_name in state.join
    )

    mappings = [orm.mappings.get(state.table.name, dict)]
    for join_on in state.join:
        join_table = state.join_tables[join_on]
        mappings.append(orm.mappings.get(join_table.element.name, dict))

    rows = []
    for row in await database.fetch_all(query):
        tables_data = tuple({} for _ in range(tables))
        for col, value in enumerate(row.values()):
            col_table, col_name = cols_mappings[col]
            tables_data[col_table][col_name] = value

        rows.append(
            tuple(
                mappings[i](**data) if data[keys[i]] is not None else None
                for i, data in enumerate(tables_data)
            )
        )

    return rows


def get_column(
    state: ObjectMapperQueryState, name: str, in_join: bool = False
) -> ColumnElement:
    if "." not in name:
        if in_join:
            return state.join_root.c[name]
        return state.table.c[name]

    join_name, name = name.rsplit(".", 1)
    return state.join[join_name].table.c[name]


def filter_query(
    state: ObjectMapperQueryState, query: ClauseElement, *, in_join: bool = False
) -> ClauseElement:
    if state.filter:
        for filter_clause in state.filter:
            if isinstance(filter_clause, dict):
                for filter_col, filter_value in filter_clause.items():
                    if "__" in filter_col:
                        col_name, expression = filter_col.split("__")
                        col = get_column(state, col_name, in_join)
                        if expression == "in":
                            query = query.where(col.in_(filter_value))
                        elif expression == "gte":
                            query = query.where(col >= filter_value)
                        elif expression == "gt":
                            query = query.where(col > filter_value)
                        elif expression == "lte":
                            query = query.where(col <= filter_value)
                        elif expression == "lt":
                            query = query.where(col < filter_value)
                        elif expression == "isnull":
                            if filter_value:
                                query = query.where(col.is_(None))
                            else:
                                query = query.where(col.isnot(None))
                    else:
                        col = get_column(state, filter_col, in_join)
                        if filter_value is True:
                            query = query.where(col.is_(True))
                        elif filter_value is False:
                            query = query.where(col.is_(False))
                        elif filter_value is None:
                            query = query.where(col.is_(None))
                        else:
                            query = query.where(col == filter_value)
            else:
                query = query.where(filter_clause)

    if state.exclude:
        for exclude_clause in state.exclude:
            if isinstance(exclude_clause, dict):
                for filter_col, filter_value in exclude_clause.items():
                    if "__" in filter_col:
                        col_name, expression = filter_col.split("__")
                        col = get_column(state, col_name, in_join)
                        if expression == "in":
                            query = query.where(not_(col.in_(filter_value)))
                        elif expression == "gte":
                            query = query.where(col < filter_value)
                        elif expression == "gt":
                            query = query.where(col <= filter_value)
                        elif expression == "lte":
                            query = query.where(col > filter_value)
                        elif expression == "lt":
                            query = query.where(col >= filter_value)
                        elif expression == "isnull":
                            if filter_value:
                                query = query.where(col.isnot(None))
                            else:
                                query = query.where(col.is_(None))
                    else:
                        col = get_column(state, filter_col, in_join)
                        if filter_value is True or filter_value is False:
                            query = query.where(col == (not filter_value))
                        else:
                            query = query.where(col != filter_value)
            else:
                query = query.where(not_(exclude_clause))

    return query


def slice_query(state: ObjectMapperQueryState, query: ClauseElement) -> ClauseElement:
    if state.offset:
        query = query.offset(state.offset)
    if state.limit:
        query = query.limit(state.limit)
    return query


def order_query(
    state: ObjectMapperQueryState, query: ClauseElement, *, in_join: bool = False
) -> ClauseElement:
    if not state.order_by:
        return query

    order_by = []
    for ordering in state.order_by:
        if ordering[0] == "-":
            col = get_column(state, ordering[1:], in_join)
            order_by.append(desc(col))
        else:
            col = get_column(state, ordering, in_join)
            order_by.append(asc(col))

    return query.order_by(*order_by)


def validate_conditions(state: ObjectMapperQueryState, conditions: Sequence[str]):
    for condition in conditions:
        if "__" in condition:
            condition, _ = condition.split("__", 1)
        if "." in condition:
            join_path, field = condition.rsplit(".", 1)
            validate_column(state.join_tables[join_path], field[0])
        else:
            validate_column(state.table, condition)


class InvalidColumnError(ValueError):
    def __init__(self, col_name: str, table: TableClause):
        valid_columns = ", ".join(table.c.keys())
        msg = (
            f"'{col_name}' is not a valid column for table '{table.name}'. "
            f"Valid columns are: {valid_columns}"
        )
        super().__init__(msg)


def validate_columns(table: TableClause, columns: Iterable[str]):
    for col_name in columns:
        if col_name not in table.c:
            raise InvalidColumnError(col_name, table)


def validate_column(table: TableClause, col_name: str):
    if col_name not in table.c:
        raise InvalidColumnError(col_name, table)
