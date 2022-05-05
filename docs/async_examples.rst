..  Copyright 2021 GridGain Systems, Inc. and Contributors.

..  Licensed under the GridGain Community Edition License (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

..      https://www.gridgain.com/products/software/community-edition/gridgain-community-edition-license

..  Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

.. _async_examples_of_usage:

============================
Asynchronous client examples
============================
File: `async_key_value.py`_.

Basic usage
-----------
Asynchronous client and cache (:py:class:`~pygridgain.aio_client.AioClient` and :py:class:`~pygridgain.aio_cache.AioCache`)
has mostly the same API as synchronous ones (:py:class:`~pygridgain.client.Client` and :py:class:`~pygridgain.cache.Cache`).
But there is some peculiarities.

Basic key-value
===============
Firstly, import dependencies.

.. literalinclude:: ../examples/async_key_value.py
  :language: python
  :lines: 19

Let's connect to cluster and perform key-value queries.

.. literalinclude:: ../examples/async_key_value.py
  :language: python
  :dedent: 4
  :lines: 24-47

Scan
====
The :py:meth:`~pygridgain.aio_cache.AioСache.scan` method returns :py:class:`~pygridgain.cursors.AioScanCursor`,
that yields the resulting rows.

.. literalinclude:: ../examples/async_key_value.py
  :language: python
  :dedent: 8
  :lines: 49-60

ExpiryPolicy
============
File: `expiry_policy.py`_.

You can enable expiry policy (TTL) by two approaches.

Firstly, expiry policy can be set for entire cache by setting :py:attr:`~pygridgain.datatypes.prop_codes.PROP_EXPIRY_POLICY`
in cache settings dictionary on creation.

.. literalinclude:: ../examples/expiry_policy.py
  :language: python
  :dedent: 12
  :lines: 74-77

.. literalinclude:: ../examples/expiry_policy.py
  :language: python
  :dedent: 12
  :lines: 83-91

Secondly, expiry policy can be set for all cache operations, which are done under decorator. To create it use
:py:meth:`~pygridgain.cache.BaseCache.with_expire_policy`

.. literalinclude:: ../examples/expiry_policy.py
  :language: python
  :dedent: 12
  :lines: 98-107

Transactions
------------
File: `transactions.py`_.

Client transactions are supported for caches with
:py:attr:`~pygridgain.datatypes.cache_config.CacheAtomicityMode.TRANSACTIONAL` mode.
**Supported only python 3.7+**

Let's create transactional cache:

.. literalinclude:: ../examples/transactions.py
  :language: python
  :dedent: 8
  :lines: 30-33

Let's start a transaction and commit it:

.. literalinclude:: ../examples/transactions.py
  :language: python
  :dedent: 8
  :lines: 36-42

Let's check that the transaction was committed successfully:

.. literalinclude:: ../examples/transactions.py
  :language: python
  :dedent: 8
  :lines: 45-46

Let's check that raising exception inside `async with` block leads to transaction's rollback

.. literalinclude:: ../examples/transactions.py
  :language: python
  :dedent: 8
  :lines: 49-61

Let's check that timed out transaction is successfully rolled back

.. literalinclude:: ../examples/transactions.py
  :language: python
  :dedent: 8
  :lines: 64-75

See more info about transaction's parameters in a documentation of :py:meth:`~pygridgain.aio_client.AioClient.tx_start`

SQL
---
File: `async_sql.py`_.

First let us establish a connection.

.. literalinclude:: ../examples/async_sql.py
  :language: python
  :dedent: 4
  :lines: 25-26

Then create tables. Begin with `Country` table, than proceed with related
tables `City` and `CountryLanguage`.

.. literalinclude:: ../examples/helpers/sql_helper.py
  :language: python
  :dedent: 4
  :lines: 28-44, 54-61, 69-75

.. literalinclude:: ../examples/async_sql.py
  :language: python
  :dedent: 4
  :lines: 28-33

Create indexes.

.. literalinclude:: ../examples/helpers/sql_helper.py
  :language: python
  :dedent: 4
  :lines: 63, 77

.. literalinclude:: ../examples/async_sql.py
  :language: python
  :dedent: 8
  :lines: 36-37

Fill tables with data.

.. literalinclude:: ../examples/helpers/sql_helper.py
  :language: python
  :dedent: 4
  :lines: 46-52, 65-67, 79-81

.. literalinclude:: ../examples/async_sql.py
  :language: python
  :dedent: 8
  :lines: 40-50

Now let us answer some questions.

What are the 10 largest cities in our data sample (population-wise)?
====================================================================

.. literalinclude:: ../examples/async_sql.py
  :language: python
  :dedent: 8
  :lines: 53-67

The :py:meth:`~pygridgain.aio_client.AioClient.sql` method returns :py:class:`~pygridgain.cursors.AioSqlFieldsCursor`,
that yields the resulting rows.

What are the 10 most populated cities throughout the 3 chosen countries?
========================================================================

If you set the `include_field_names` argument to `True`, the
:py:meth:`~pygridgain.client.Client.sql` method will generate a list of
column names as a first yield. Unfortunately, there is no async equivalent of `next` but
you can await :py:meth:`__anext__()`
of :py:class:`~pygridgain.cursors.AioSqlFieldsCursor`

.. literalinclude:: ../examples/async_sql.py
  :language: python
  :dedent: 8
  :lines: 70-96

Display all the information about a given city
==============================================

.. literalinclude:: ../examples/async_sql.py
  :language: python
  :dedent: 8
  :lines: 99-111

Finally, delete the tables used in this example with the following queries:

.. literalinclude:: ../examples/helpers/sql_helper.py
  :language: python
  :dedent: 4
  :lines: 83

.. literalinclude:: ../examples/async_sql.py
  :language: python
  :dedent: 8
  :lines: 114-116



.. _expiry_policy.py: https://github.com/gridgain/python-thin-client/blob/master/examples/expiry_policy.py
.. _async_key_value.py: https://github.com/gridgain/python-thin-client/blob/master/examples/async_key_value.py
.. _async_sql.py: https://github.com/gridgain/python-thin-client/blob/master/examples/async_sql.py
.. _transactions.py: https://github.com/gridgain/python-thin-client/blob/master/examples/transactions.py
