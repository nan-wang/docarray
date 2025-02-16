from itertools import product

import numpy as np
import pytest

from docarray import DocumentArray, Document
from docarray.math import ndarray
import operator


@pytest.mark.parametrize(
    'storage, config',
    [
        ('memory', None),
        ('weaviate', {'n_dim': 32}),
        ('annlite', {'n_dim': 32}),
        ('qdrant', {'n_dim': 32}),
        ('elasticsearch', {'n_dim': 32}),
    ],
)
@pytest.mark.parametrize('limit', [1, 5, 10])
@pytest.mark.parametrize(
    'query',
    [np.random.random(32), np.random.random((1, 32)), np.random.random((2, 32))],
)
def test_find(storage, config, limit, query, start_storage):
    embeddings = np.random.random((20, 32))

    if config:
        da = DocumentArray(storage=storage, config=config)
    else:
        da = DocumentArray(storage=storage)

    da.extend([Document(embedding=v) for v in embeddings])

    result = da.find(query, limit=limit)
    n_rows_query, n_dim = ndarray.get_array_rows(query)

    if n_rows_query == 1 and n_dim == 1:
        # we expect a result to be DocumentArray
        assert len(result) == limit
    elif n_rows_query == 1 and n_dim == 2:
        # we expect a result to be a list with 1 DocumentArray
        assert len(result) == 1
        assert len(result[0]) == limit
    else:
        # check for each row on the query a DocumentArray is returned
        assert len(result) == n_rows_query

    # check returned objects are sorted according to the storage backend metric
    # weaviate uses cosine similarity by default
    # annlite uses cosine distance by default
    if n_dim == 1:
        if storage == 'weaviate':
            cosine_similarities = [
                t['cosine_similarity'].value for t in result[:, 'scores']
            ]
            assert sorted(cosine_similarities, reverse=True) == cosine_similarities
        elif storage in ['memory', 'annlite', 'elasticsearch']:
            cosine_distances = [t['cosine'].value for t in da[:, 'scores']]
            assert sorted(cosine_distances, reverse=False) == cosine_distances
    else:
        if storage == 'weaviate':
            for da in result:
                cosine_similarities = [
                    t['cosine_similarity'].value for t in da[:, 'scores']
                ]
                assert sorted(cosine_similarities, reverse=True) == cosine_similarities
        elif storage in ['memory', 'annlite', 'elasticsearch']:
            for da in result:
                cosine_distances = [t['cosine'].value for t in da[:, 'scores']]
                assert sorted(cosine_distances, reverse=False) == cosine_distances


@pytest.mark.parametrize(
    'storage, config',
    [
        ('elasticsearch', {'n_dim': 32, 'index_text': True}),
    ],
)
def test_find_by_text(storage, config, start_storage):
    da = DocumentArray(storage=storage, config=config)
    da.extend(
        [
            Document(id='1', text='token1 token2 token3'),
            Document(id='2', text='token1 token2'),
            Document(id='3', text='token2 token3 token4'),
        ]
    )

    results = da.find('token1')
    assert isinstance(results, DocumentArray)
    assert len(results) == 2
    assert set(results[:, 'id']) == {'1', '2'}

    results = da.find('token2 token3')
    assert isinstance(results, DocumentArray)
    assert len(results) == 3
    assert set(results[:, 'id']) == {'1', '2', '3'}

    results = da.find('token3 token4')
    assert isinstance(results, DocumentArray)
    assert len(results) == 2
    assert set(results[:, 'id']) == {'1', '3'}
    results = da.find('token3 token4', limit=1)
    assert len(results) == 1

    results = da.find(['token4', 'token'])
    assert isinstance(results, list)
    assert len(results) == 2  # len(input) = len(output)
    assert len(results[0]) == 1  # 'token4' only appears in one doc
    assert results[0][0].id == '3'  # 'token4' only appears in doc3
    assert len(results[1]) == 0  # 'token' is not present in da vocabulary


@pytest.mark.parametrize(
    'storage, config',
    [
        ('elasticsearch', {'n_dim': 32, 'tag_indices': ['attr1', 'attr2', 'attr3']}),
    ],
)
def test_find_by_tag(storage, config, start_storage):
    da = DocumentArray(storage=storage, config=config)
    da.extend(
        [
            Document(
                id='1',
                tags={
                    'attr1': 'token1 token2 token3',
                    'attr2': 'token2 token3 token4',
                    'attr3': 'token4 token5 token6',
                },
            ),
            Document(
                id='2',
                tags={
                    'attr1': 'token1',
                    'attr2': 'token2',
                    'attr3': 'token6',
                },
            ),
            Document(
                id='3',
                tags={
                    'attr1': 'token4',
                    'attr2': 'token3',
                    'attr3': 'token1 token5',
                },
            ),
            Document(id='4'),
        ]
    )

    results = da.find('token1 token2', index='attr1')
    assert isinstance(results, DocumentArray)
    assert len(results) == 2
    assert results[0].id == '1'
    assert results[1].id == '2'

    results = da.find('token1 token2', index='attr1', limit=1)
    assert len(results) == 1

    results = da.find('token2 token4', index='attr1')
    assert len(results) == 2
    assert set(results[:, 'id']) == {'1', '3'}

    results = da.find('token4', index='attr2')
    assert len(results) == 1
    assert results[0].id == '1'

    results = da.find('token6', index='attr3')
    assert len(results) == 2
    assert results[0].id == '2'
    assert results[1].id == '1'

    results = da.find('token6', index='attr3', limit=1)
    assert len(results) == 1

    results = da.find('token5', index='attr3')
    assert len(results) == 2
    assert set(results[:, 'id']) == {'1', '3'}
    assert all(['token5' in r.tags['attr3'] for r in results]) == True

    results = da.find('token1', index='attr3')
    assert len(results) == 1
    assert results[0].id == '3'
    assert all(['token1' in r.tags['attr3'] for r in results]) == True

    results = da.find(['token1 token2'], index='attr1')
    assert isinstance(results, list)
    assert len(results) == 1
    assert isinstance(results[0], DocumentArray)

    results = da.find(['token1 token2', 'token1'], index='attr1')
    assert isinstance(results, list)
    assert len(results) == 2
    assert all([isinstance(result, DocumentArray) for result in results]) == True


numeric_operators_annlite = {
    '$gte': operator.ge,
    '$gt': operator.gt,
    '$lte': operator.le,
    '$lt': operator.lt,
    '$eq': operator.eq,
    '$neq': operator.ne,
}

numeric_operators_weaviate = {
    'GreaterThanEqual': operator.ge,
    'GreaterThan': operator.gt,
    'LessThanEqual': operator.le,
    'LessThan': operator.lt,
    'Equal': operator.eq,
    'NotEqual': operator.ne,
}


numeric_operators_qdrant = {
    'gte': operator.ge,
    'gt': operator.gt,
    'lte': operator.le,
    'lt': operator.lt,
    'eq': operator.eq,
    'neq': operator.ne,
}


@pytest.mark.parametrize(
    'storage,filter_gen,numeric_operators,operator',
    [
        *[
            tuple(
                [
                    'weaviate',
                    lambda operator, threshold: {
                        'path': ['price'],
                        'operator': operator,
                        'valueInt': threshold,
                    },
                    numeric_operators_weaviate,
                    operator,
                ]
            )
            for operator in numeric_operators_weaviate.keys()
        ],
        *[
            tuple(
                [
                    'qdrant',
                    lambda operator, threshold: {
                        'must': [{'key': 'price', 'range': {operator: threshold}}]
                    },
                    numeric_operators_qdrant,
                    operator,
                ]
            )
            for operator in ['gte', 'gt', 'lte', 'lt']
        ],
        tuple(
            [
                'qdrant',
                lambda operator, threshold: {
                    'must': [{'key': 'price', 'match': {'value': threshold}}]
                },
                numeric_operators_qdrant,
                'eq',
            ]
        ),
        tuple(
            [
                'qdrant',
                lambda operator, threshold: {
                    'must_not': [{'key': 'price', 'match': {'value': threshold}}]
                },
                numeric_operators_qdrant,
                'neq',
            ]
        ),
        *[
            tuple(
                [
                    'annlite',
                    lambda operator, threshold: {'price': {operator: threshold}},
                    numeric_operators_annlite,
                    operator,
                ]
            )
            for operator in numeric_operators_annlite.keys()
        ],
    ],
)
def test_search_pre_filtering(
    storage, filter_gen, operator, numeric_operators, start_storage
):
    n_dim = 128
    da = DocumentArray(
        storage=storage, config={'n_dim': n_dim, 'columns': [('price', 'int')]}
    )

    da.extend(
        [
            Document(id=f'r{i}', embedding=np.random.rand(n_dim), tags={'price': i})
            for i in range(50)
        ]
    )
    thresholds = [10, 20, 30]

    for threshold in thresholds:

        filter = filter_gen(operator, threshold)

        results = da.find(np.random.rand(n_dim), filter=filter)

        assert len(results) > 0

        assert all(
            [numeric_operators[operator](r.tags['price'], threshold) for r in results]
        )


@pytest.mark.parametrize(
    'storage,filter_gen,numeric_operators,operator',
    [
        *[
            tuple(
                [
                    'weaviate',
                    lambda operator, threshold: {
                        'path': ['price'],
                        'operator': operator,
                        'valueNumber': threshold,
                    },
                    numeric_operators_weaviate,
                    operator,
                ]
            )
            for operator in numeric_operators_weaviate.keys()
        ]
    ],
)
def test_filtering(storage, filter_gen, operator, numeric_operators, start_storage):
    n_dim = 128
    da = DocumentArray(
        storage=storage, config={'n_dim': n_dim, 'columns': [('price', 'float')]}
    )

    da.extend([Document(id=f'r{i}', tags={'price': i}) for i in range(50)])
    thresholds = [10, 20, 30]

    for threshold in thresholds:

        filter = filter_gen(operator, threshold)
        results = da.find(filter=filter)

        assert all(
            [numeric_operators[operator](r.tags['price'], threshold) for r in results]
        )


def test_weaviate_filter_query(start_storage):
    n_dim = 128
    da = DocumentArray(
        storage='weaviate', config={'n_dim': n_dim, 'columns': [('price', 'int')]}
    )

    da.extend(
        [
            Document(id=f'r{i}', embedding=np.random.rand(n_dim), tags={'price': i})
            for i in range(50)
        ]
    )

    with pytest.raises(ValueError):
        da.find(np.random.rand(n_dim), filter={'wrong': 'filter'})

    with pytest.raises(ValueError):
        da._filter(filter={'wrong': 'filter'})

    assert isinstance(da._filter(filter={}), type(da))


@pytest.mark.parametrize('storage', ['memory', 'elasticsearch'])
def test_unsupported_pre_filtering(storage, start_storage):

    n_dim = 128
    da = DocumentArray(
        storage=storage, config={'n_dim': n_dim, 'columns': [('price', 'int')]}
    )

    da.extend(
        [
            Document(id=f'r{i}', embedding=np.random.rand(n_dim), tags={'price': i})
            for i in range(50)
        ]
    )

    with pytest.raises(ValueError):
        da.find(np.random.rand(n_dim), filter={'price': {'$gte': 2}})
