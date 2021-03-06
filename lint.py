#!/usr/bin/python2
#
# Copyright 2011 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A schema linter, connects to a running mysql and checks for common errors."""

__author__ = 'flamingcow@google.com (Ian Gulliver)'

from pylib import app
from pylib import db

import gflags

FLAGS = gflags.FLAGS

gflags.DEFINE_string('db', None, 'DB spec to scan')


def _ListStartsWith(superset, subset):
  """Returns true if superset starts with subset."""
  return superset[:len(subset)] == subset


def FindNonTransactionalTables(dbh):
  tables = dbh.ExecuteOrDie(
      'SELECT TABLE_SCHEMA, TABLE_NAME, ENGINE FROM INFORMATION_SCHEMA.TABLES'
      ' WHERE TABLE_SCHEMA NOT IN ("mysql", "information_schema")'
      ' AND ENGINE IN ("MyISAM")')

  for table in tables:
    print '`%s`.`%s`: Non-transactional engine %s' % (
        table['TABLE_SCHEMA'], table['TABLE_NAME'], table['ENGINE'])


def FindDuplicateIndexes(dbh):
  tables = dbh.ExecuteOrDie(
      'SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES')

  for table in tables:
    index_columns = dbh.ExecuteOrDie('SHOW INDEX FROM `%s`.`%s`' %
                                     (table['TABLE_SCHEMA'],
                                      table['TABLE_NAME']))
    indexes = {}
    for column in index_columns:
      index = indexes.setdefault(column['Key_name'], {})
      index['unique'] = not bool(column['Non_unique'])
      index.setdefault('columns', []).append(column['Column_name'])

    for key_name1, index1 in indexes.iteritems():
      if index1['unique']:
        # We never suggest removal of unique indexes.
        continue
      for key_name2, index2 in indexes.iteritems():
        if key_name1 == key_name2:
          continue
        if _ListStartsWith(index2['columns'], index1['columns']):
          print '`%s`.`%s`: Key %s is a prefix of %s' % (
              table['TABLE_SCHEMA'], table['TABLE_NAME'],
              key_name1, key_name2)

    if 'PRIMARY' in indexes and len(indexes['PRIMARY']['columns']) == 1:
      # Single-column primary index. Validate type.
      column_info = dbh.ExecuteOrDie(
          'SHOW COLUMNS FROM `%s`.`%s` LIKE %%(column)s' %
          (table['TABLE_SCHEMA'],
           table['TABLE_NAME']),
          {'column': indexes['PRIMARY']['columns'][0]})
      if column_info[0]['Null'] == 'YES':
        print '`%s`.`%s`: ID column %s is nullable' % (
            table['TABLE_SCHEMA'], table['TABLE_NAME'],
            column_info[0]['Field'])
      if column_info[0]['Type'] not in ('bigint(20)',
                                        'bigint(20) unsigned'):
        print '`%s`.`%s`: ID column %s has invalid type: %s' % (
            table['TABLE_SCHEMA'], table['TABLE_NAME'],
            column_info[0]['Field'], column_info[0]['Type'])


def main(unused_argv):
  assert FLAGS.db, 'Please pass --db'

  with db.Connect(FLAGS.db) as dbh:
    FindDuplicateIndexes(dbh)
    FindNonTransactionalTables(dbh)


if __name__ == '__main__':
  app.run()
