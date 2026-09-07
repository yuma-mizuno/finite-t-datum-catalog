"""Check source links, hashes, generated record consistency and HTML packaging."""
import hashlib
import json
from pathlib import Path
import re
import zipfile
import gzip

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
data=json.loads((HERE/'catalogue.json').read_text(encoding='utf-8'))
schema=json.loads((HERE/'record.schema.json').read_text(encoding='utf-8'))
try:
    import jsonschema
except ImportError:
    jsonschema=None
if jsonschema is not None:
    # All references are local fragments. Omitting the informational base URI
    # also works with older offline jsonschema resolvers.
    local_schema=dict(schema);local_schema.pop('$id',None)
    validator=jsonschema.Draft202012Validator(local_schema)
    validator.check_schema(local_schema)
    for record in data['records']:validator.validate(record)
    print(f'PASS: JSON Schema draft 2020-12 validation for all {len(data["records"])} records.')
html=(HERE/'index.html').read_text(encoding='utf-8')
embedded=re.search(r'<script id="catalogue-data" type="application/json">(.*?)</script>',html,re.S).group(1)
assert json.loads(embedded)==data
assert not re.search(r'<script[^>]+src=|<link[^>]+href=',html)
assert not re.search(r'/\*__[A-Z]+__\*/',html)
files=list((HERE/'records').glob('*.json'))
assert len(files)==len(data['records'])
assert [sum(r['rank']==rank and r['scope']['symmetrizer']=='identity' for r in data['records']) for rank in (1,2,3,4,5,6)]==[2,6,16,37,55,108]
assert len(data['records'])==224+sum(r['new_nonidentity_families'] for r in data['symmetrizable_classifications'])
# Catalogue IDs and displayed numbers share one sequence per rank.
ids={r['id'] for r in data['records']}
source_ids={r['id']:r['provenance']['source_record_id'] for r in data['records']}
def source_references(value):
    if isinstance(value,str):return source_ids.get(value,value)
    if isinstance(value,list):return [source_references(x) for x in value]
    if isinstance(value,dict):return {source_ids.get(k,k):source_references(v) for k,v in value.items()}
    return value
for rank in sorted({r['rank'] for r in data['records']}):
    group=[r for r in data['records'] if r['rank']==rank]
    assert [r['class_number'] for r in group]==list(range(1,len(group)+1))
    assert [r['id'] for r in group]==[f'r{rank}-c{i:02d}' for i in range(1,len(group)+1)]
    source_path=ROOT/f'research/symmetrizable/rank{rank}/catalogue-records.json'
    source_records={x['id']:x for x in json.loads(source_path.read_text())} if source_path.exists() else {}
    for r in group:
        assert r['schema_version']=='3.0.0'
        assert r['id']+':' in (ROOT/r['exponents']['plot_path']).read_text(encoding='utf8')
        source_id=r['provenance']['source_record_id']
        if r['scope']['symmetrizer']=='positive_diagonal':
            original=source_records[source_id]
            assert original['class_number']==r['provenance']['source_class_number']
            for key in ('datum','family','periodicity','exchange','slice','matrix_ratios','verification'):
                assert original[key]==source_references(r[key]),(r['id'],key)
        for match in r['notes']['family']['identifications']:
            if match.get('folding'):assert match['folding']['parent_record'] in ids
assert len({(r['rank'],r['class_number']) for r in data['records']})==len(data['records'])
print('PASS: one class sequence per rank, canonical IDs and SVG labels, source identity and unchanged mathematical records.')

hashes={}
with zipfile.ZipFile(ROOT/'research/rank4/smt_queries.zip') as archive:
    archive_names=archive.namelist()
    for r in data['records']:
        assert set(schema['required'])<=set(r)
        assert json.loads((HERE/'records'/f'{r["id"]}.json').read_text(encoding='utf-8'))==r
        for source in r['provenance']['sources']+r['provenance']['enrichment_sources']:
            p=ROOT/source['path']
            if p not in hashes: hashes[p]=hashlib.sha256(p.read_bytes()).hexdigest()
            assert hashes[p]==source['sha256']
        assert (ROOT/r['exponents']['plot_path']).is_file()
        assert r['verification']['jacobian_spectrum']=='independent interval-certified match'
        assert sum(x['multiplicity'] for x in r['exponents']['multiplicities'])==r['slice']['vertices']
        for key in ('manuscript','pdf','query_path'):
            if r['provenance'][key]:assert (ROOT/r['provenance'][key]).is_file(),r['provenance'][key]
        weighted=r['scope']['symmetrizer']=='positive_diagonal'
        if r['rank']<3 and not weighted:continue
        if r['rank']==4 and not weighted:
            member=r['provenance']['query_member']
            names=[x for x in archive_names if x==member or x.endswith('/'+member)]
            assert len(names)==1,(member,names)
            query=archive.read(names[0])
        elif weighted or r['rank']>=5:
            with zipfile.ZipFile(ROOT/r['provenance']['query_path']) as higher_archive:
                query=gzip.decompress(higher_archive.read(r['provenance']['query_member']))
        else:
            query=(ROOT/r['provenance']['query_path']).read_bytes()
            if r['provenance']['query_path'].endswith('.gz'):query=gzip.decompress(query)
        assert hashlib.sha256(query).hexdigest()==r['family']['coverage']['sha256']
print(f'PASS: {len(files)} standalone records, embedded catalogue, source links and SHA-256 provenance, including every coverage query.')
