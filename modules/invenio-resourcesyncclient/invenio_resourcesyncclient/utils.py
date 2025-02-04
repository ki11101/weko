# -*- coding: utf-8 -*-
#
# This file is part of WEKO3.
# Copyright (C) 2017 National Institute of Informatics.
#
# WEKO3 is free software; you can redistribute it
# and/or modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# WEKO3 is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with WEKO3; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place, Suite 330, Boston,
# MA 02111-1307, USA.

"""WEKO3 module docstring."""
import json
import ssl
import traceback
from datetime import datetime as dt
from sys import path
from urllib.parse import parse_qs, urlencode, urlparse, urlsplit, urlunsplit

import dateutil
from flask import current_app, jsonify
from frozendict import frozendict
from invenio_db import db
from invenio_oaiharvester.harvester import DCMapper, DDIMapper, JPCOARMapper
from invenio_oaiharvester.tasks import event_counter, map_indexes
from invenio_oaiharvester.utils import ItemEvents
from invenio_pidstore.models import PersistentIdentifier, PIDStatus
from invenio_records.models import RecordMetadata
from lxml import etree
from resync.client import Client
from resync.client_utils import init_logging, url_or_file_open
from resync.mapper import MapperError
from resync.resource_list_builder import ResourceListBuilder
from resync.sitemap import Sitemap
from weko_deposit.api import WekoDeposit
from weko_records_ui.utils import soft_delete

from .config import INVENIO_RESYNC_ENABLE_ITEM_VERSIONING, \
    INVENIO_RESYNC_INDEXES_MODE, INVENIO_RESYNC_MODE

ssl._create_default_https_context = ssl._create_unverified_context


def read_capability(url):
    """Read capability of an url."""
    s = Sitemap()
    capability = None
    try:
        document = s.parse_xml(url_or_file_open(url))
    except IOError as e:
        raise e
    if 'capability' in document.md:
        capability = document.md['capability']
    return capability


def sync_baseline(_map, base_url, counter, dryrun=False,
                  from_date=None, to_date=None):
    """Run resync baseline."""
    from .resync import ResourceSyncClient
    client = ResourceSyncClient()
    # ignore fail to continue running, log later
    client.ignore_failures = True
    init_logging(verbose=True)
    try:
        if from_date:
            base_url = set_query_parameter(base_url, 'from_date', from_date)
        if to_date:
            base_url = set_query_parameter(base_url, 'to_date', to_date)
        # set sitemap_name to specify the only url to sync
        # set mappings to specify the url will
        # be used to validate subitem in resync library
        client.sitemap_name = base_url
        client.dryrun = dryrun
        client.set_mappings(_map)
        result = client.baseline_or_audit()
        current_app.logger.debug('{0} {1} {2}: {3}'.format(
            __file__, 'sync_baseline()', 'result', result))
        update_counter(counter, result)
        return True
    except MapperError:
        # if mapper error then remove one element in url and retry
        current_app.logger.info('MapperError')
        paths = _map[0].rsplit('/', 1)
        _map[0] = paths[0]
        return False
    except Exception as e:
        current_app.logger.error('Error when Sync :' + str(e))
        return False


def sync_audit(_map, counter):
    """Run resync audit."""
    client = Client()
    # ignore fail to continue running, log later
    client.ignore_failures = True
    client.set_mappings(_map)
    # init_logging(verbose=True)
    src_resource_list = client.find_resource_list()
    rlb = ResourceListBuilder(mapper=client.mapper)
    dst_resource_list = rlb.from_disk()
    # Compare these resource lists respecting any comparison options
    (same, updated, deleted, created) = dst_resource_list.compare(
        src_resource_list)
    result = dict(
        created=[],
        updated=[],
        deleted=[]
    )
    for item in created:
        record_id = item.uri.rsplit('/', 1)[1]
        result['created'].append(record_id)
    for item in updated:
        record_id = item.uri.rsplit('/', 1)[1]
        result['updated'].append(record_id)
    for item in deleted:
        record_id = item.uri.rsplit('/', 1)[1]
        result['deleted'].append(record_id)
    update_counter(counter, result)
    return dict(
        same=len(same),
        updated=len(updated),
        deleted=len(deleted),
        created=len(created)
    )


def sync_incremental(_map, counter, base_url, from_date, to_date):
    """Run resync incremental."""
    # init_logging(verbose=True)
    from .resync import ResourceSyncClient
    client = ResourceSyncClient()
    client.ignore_failures = True
    try:
        single_sync_incremental(_map, counter, base_url, from_date, to_date)
        return True
    except MapperError as e:
        current_app.logger.info(e)
        paths = _map[0].rsplit('/', 1)
        _map[0] = paths[0]
    except Exception as e:
        # maybe url contain a list of changelist, instead of changelist
        current_app.logger.info(e)
        s = Sitemap()
        try:
            docs = s.parse_xml(url_or_file_open(base_url))
        except IOError as ioerror:
            raise ioerror
        if docs:
            for doc in docs:
                # make sure sub url is a changelist/ changedump
                capability = read_capability(doc.uri)
                if capability is None:
                    raise('Bad URL, not a changelist/changedump,'
                          ' cannot sync incremental')
                if capability != 'changelist' and capability != 'changedump':
                    raise ('Bad URL, not a changelist/changedump,'
                           ' cannot sync incremental')
                single_sync_incremental(_map, counter,
                                        doc.uri, from_date, to_date)
            return True
        raise e


def single_sync_incremental(_map, counter, url, from_date, to_date):
    """Run resync incremental for 1 changelist url only."""
    from .resync import ResourceSyncClient
    if from_date:
        url = set_query_parameter(url, 'from_date', from_date)
    else:
        from_date = get_from_date_from_url(url)
    if to_date:
        url = set_query_parameter(url, 'to_date', to_date)
    client = ResourceSyncClient()
    client.ignore_failures = True
    parts = urlsplit(_map[0])
    uri_host = urlunsplit([parts[0], parts[1], '', '', ''])
    sync_result = False
    while _map[0] != uri_host and not sync_result:
        try:
            client.set_mappings(_map)
            result = client.incremental(
                change_list_uri=url,
                from_datetime=from_date
            )
            update_counter(counter, result)
            sync_result = True
        except MapperError as e:
            # if error then remove one element in url and retry
            current_app.logger.info('MapperError')
            paths = _map[0].rsplit('/', 1)
            _map[0] = paths[0]


def set_query_parameter(url, param_name, param_value):
    """Given a URL.

    set or replace a query parameter and return the modified URL.
    """
    scheme, netloc, path, query_string, fragment = urlsplit(url)
    query_params = parse_qs(query_string)

    query_params[param_name] = [param_value]
    new_query_string = urlencode(query_params, doseq=True)

    return urlunsplit((scheme, netloc, path, new_query_string, fragment))


def get_list_records(resync_id):
    """Get list records in local dir. Only get updated."""
    from .api import ResyncHandler
    resync_index = ResyncHandler.get_resync(resync_id)
    records = []
    if not resync_index.result:
        return records
    records = json.loads(resync_index.result)
    # current_app.logger.debug('{0} {1} {2}: {3}'.format(
    #     __file__, 'get_list_records()', 'records', records))
    return records


def process_item(record, resync, counter):
    """Process item."""
    current_app.logger.debug('{0} {1} {2}: {3}'.format(
        __file__, 'start process_item()', record, counter))
    event_counter('processed_items', counter)
    event = ItemEvents.INIT
    xml = etree.tostring(record, encoding='utf-8').decode()
    # current_app.logger.debug('{0} {1} {2}: {3}'.format(
    #     __file__, 'process_item()', 'xml', xml))

    mapper = JPCOARMapper(xml)

    current_app.logger.debug('{0} {1} {2}: {3}'.format(
        __file__, 'process_item()', 'mapper.identifier()', mapper.identifier()))

    resyncid = PersistentIdentifier.query.filter_by(
        pid_type='syncid', pid_value=gen_resync_pid_value(
            resync,
            mapper.identifier()
        )).with_lockmode('update').one_or_none()

    indexes = []
    current_app.logger.debug('{0} {1} {2}: {3}'.format(
        __file__, 'process_item()', 'resyncid', resyncid))

    if resyncid is None:
        dep = WekoDeposit.create({})
        pid = PersistentIdentifier.create(pid_type='syncid',
                                          pid_value=gen_resync_pid_value(
                                              resync,
                                              mapper.identifier()
                                          ),
                                          status=PIDStatus.REGISTERED,
                                          object_type=dep.pid.object_type,
                                          object_uuid=dep.pid.object_uuid)
        current_app.logger.debug('{0} {1} {2}: {3}'.format(
            __file__, 'process_item()', 'Create pid', pid))
        indexes.append(str(resync.index_id)) if str(
            resync.index_id) not in indexes else None
        json = mapper.map()
        json['$schema'] = '/items/jsonschema/' + str(mapper.itemtype.id)
        dep['_deposit']['status'] = 'draft'
        dep.update({'actions': 'publish', 'index': indexes}, json)
        dep.commit()
        dep.publish()

        # add item versioning
        recid = PersistentIdentifier.query.filter_by(
            pid_type='recid', pid_value=dep.pid.pid_value).one_or_none()
        current_app.logger.debug('{0} {1} {2}: {3}'.format(
            __file__, 'process_item()', 'recid', recid))
        with current_app.test_request_context() as ctx:
            first_ver = dep.newversion(recid)
            first_ver.publish()
        event = ItemEvents.CREATE
    else:
        if mapper.is_deleted():
            recid = PersistentIdentifier.query.filter_by(
                pid_type='recid', object_uuid=resyncid.object_uuid).one_or_none()
            current_app.logger.debug('{0} {1} {2}: {3}'.format(
                __file__, 'process_item()', 'Delete recid', recid))
            soft_delete(recid.pid_value)
            event = ItemEvents.DELETE
        else:
            r = RecordMetadata.query.filter_by(
                id=resyncid.object_uuid).one_or_none()
            recid = PersistentIdentifier.query.filter_by(
                pid_type='recid', object_uuid=resyncid.object_uuid).one_or_none()
            current_app.logger.debug('{0} {1} {2}: {3}'.format(
                __file__, 'process_item()', 'Update recid', recid))
            # current_app.logger.debug('{0} {1} {2}: {3}'.format(
            #     __file__, 'process_item()', 'RecordMetadata', r))
            recid.status = PIDStatus.REGISTERED
            dep = WekoDeposit(r.json, r)
            if 'path' in dep:
                indexes = dep['path'].copy()
            indexes.append(str(resync.index_id)) if str(
                resync.index_id) not in indexes else None
            json = mapper.map()
            json['$schema'] = '/items/jsonschema/' + str(mapper.itemtype.id)
            dep['_deposit']['status'] = 'draft'
            dep.update({'actions': 'publish', 'index': indexes}, json)
            dep.commit()
            dep.publish()
            # current_app.logger.debug('{0} {1} {2}: {3}'.format(
            #     __file__, 'process_item()', 'WekoDeposit', dep))
            # add item versioning
            pid = PersistentIdentifier.query.filter_by(
                pid_type='recid', pid_value=dep.pid.pid_value).first()
            idt_list = mapper.identifiers
            from weko_workflow.utils import IdentifierHandle
            idt = IdentifierHandle(pid.object_uuid)
            for it in idt_list:
                if not it.get('type'):
                    continue
                pid_type = it['type'].lower()
                pid_obj = idt.get_pidstore(pid_type)
                if not pid_obj:
                    idt.register_pidstore(pid_type, it['identifier'])

            # add item versioning
            if INVENIO_RESYNC_ENABLE_ITEM_VERSIONING:
                with current_app.test_request_context() as ctx:
                    first_ver = dep.newversion(pid)
                    first_ver.publish()
            event = ItemEvents.UPDATE

    db.session.commit()

    if event == ItemEvents.CREATE:
        event_counter('created_items', counter)
    elif event == ItemEvents.UPDATE:
        event_counter('updated_items', counter)
    elif event == ItemEvents.DELETE:
        event_counter('deleted_items', counter)
    current_app.logger.debug('{0} {1} {2}: {3}'.format(
        __file__, 'end process_item()', record, counter))


def process_sync(resync_id, counter):
    """Process sync."""
    from .api import ResyncHandler
    resync_index = ResyncHandler.get_resync(resync_id)
    if not resync_index:
        raise ValueError('No Resync Index found')
    base_url = resync_index.base_url
    capability = read_capability(base_url)
    mode = resync_index.resync_mode
    save_dir = resync_index.resync_save_dir
    _map = [base_url]
    if save_dir:
        _map.append(save_dir)
    parts = urlsplit(_map[0])
    uri_host = urlunsplit([parts[0], parts[1], '', '', ''])
    from_date = resync_index.from_date
    to_date = resync_index.to_date
    current_app.logger.debug(
        '{0} {1} {2}'.format(__file__, 'process_sync', _map))
    try:
        if mode == current_app.config.get(
            'INVENIO_RESYNC_INDEXES_MODE',
            INVENIO_RESYNC_INDEXES_MODE
        ).get('baseline'):
            if not capability:
                raise ValueError('Bad URL')
            if capability != 'resourcelist' and capability != 'resourcedump':
                raise ValueError('Bad URL')
            result = False
            while _map[0] != uri_host and not result:
                result = sync_baseline(_map=_map,
                                       base_url=base_url,
                                       counter=counter,
                                       dryrun=False,
                                       from_date=from_date,
                                       to_date=to_date)
            tmp = get_list_records(resync_id)
            tmp.extend(counter.get('list'))
            new_result = list(map(json.loads, set(map(json.dumps, tmp))))
            resync_index.update({
                'result': json.dumps(new_result)
            })
            return jsonify(success=True)
        elif mode == current_app.config.get(
            'INVENIO_RESYNC_INDEXES_MODE',
            INVENIO_RESYNC_INDEXES_MODE
        ).get('audit'):
            if not capability:
                raise ValueError('Bad URL')
            if capability != 'resourcelist' and capability != 'changelist':
                raise ValueError('Bad URL')
            # do the same logic with Baseline
            # to make sure right url is used
            result = False
            while _map[0] != uri_host and not result:
                result = sync_baseline(_map=_map,
                                       base_url=base_url,
                                       counter=counter,
                                       dryrun=True)
            audit_result = sync_audit(_map, counter)
            new_result = list(set(
                get_list_records(resync_id) + counter.get('list')
            ))
            resync_index.update({
                'result': json.dumps(new_result)
            })
            return jsonify(audit_result)
        elif mode == current_app.config.get(
            'INVENIO_RESYNC_INDEXES_MODE',
            INVENIO_RESYNC_INDEXES_MODE
        ).get('incremental'):
            if not capability:
                raise (
                    'Bad URL, not a changelist/changedump,'
                    ' cannot sync incremental')
            if capability != 'changelist' and capability != 'changedump':
                raise (
                    'Bad URL, not a changelist/changedump,'
                    ' cannot sync incremental')
            result = False
            while _map[0] != uri_host and not result:
                result = sync_incremental(_map, counter,
                                          base_url, from_date, to_date)
            new_result = list(
                set(get_list_records(resync_id) + counter.get('list')))
            resync_index.update({
                'result': json.dumps(new_result)
            })
            return jsonify({'result': result})
    except Exception as e:
        current_app.logger.error(traceback.format_exc())
        return jsonify({'status': 'error', 'message': str(e)})


def update_counter(counter, result):
    """Update sync result to counter."""
    list_item = []
    list_resources = []
    counter.update({'created_items': len(result.get('created'))})
    counter.update({'updated_items': len(result.get('updated'))})
    counter.update({'deleted_items': len(result.get('deleted'))})
    counter.update({'resource_items': len(result.get('resource'))})
    if result.get('created'):
        for item in result.get('created'):
            list_item.append(item)
    if result.get('updated'):
        for item in result.get('updated'):
            list_item.append(item)
    if result.get('deleted'):
        for item in result.get('deleted'):
            list_item.append(item)
    if result.get('resource'):
        for rc in result.get('resource'):
            list_resources.append(rc)
    #counter.update({'list': list_item})
    counter.update({'list': list_resources})


def get_from_date_from_url(url):
    """Get smallest timestamp from url and parse to string."""
    s = Sitemap()
    try:
        document = s.parse_xml(url_or_file_open(url))
    except IOError as e:
        raise e
    date_list = []
    for item in document.resources:
        if item.timestamp:
            date_list.append(item.timestamp)
    if len(date_list) > 0:
        from_date = dt.fromtimestamp(min(date_list))
        return from_date.strftime("%Y-%m-%d")


def gen_resync_pid_value(resync, pid):
    """Get resync pid value."""
    if INVENIO_RESYNC_MODE:
        result = pid
    else:
        hostname = urlparse(resync.base_url)
        result = '{}://{}-{}'.format(
            hostname.scheme,
            hostname.netloc,
            pid
        )
    current_app.logger.debug('{0} {1} {2}: {3}'.format(
        __file__, 'gen_resync_pid_value()', 'result', result))
    return result
