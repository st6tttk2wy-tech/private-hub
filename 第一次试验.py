# -*- coding: utf-8 -*-
"""
第一次试验 - 数据集成系统（完整打包版）
========================================
提取、解析并整合多源数据到统一格式

版本: 1.0
创建时间: 2026-06-12
作者: MiMoCode

使用方法:
    python 第一次试验.py

功能特性:
    - 多数据源支持：SQLite数据库、REST API、CSV/JSON/XML文件
    - 数据解析：自动检测格式并解析
    - 数据转换：支持10+种转换规则
    - Web界面：可视化数据管理
"""

import csv
import json
import os
import sys
import uuid
import hashlib
import logging
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from io import StringIO
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Generator, List, Optional, Type

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# 第一部分：数据模型定义
# ============================================================================

class DataSourceType(Enum):
    """数据源类型枚举"""
    DATABASE = "database"
    API = "api"
    FILE_CSV = "file_csv"
    FILE_JSON = "file_json"
    FILE_XML = "file_xml"
    CUSTOM = "custom"


class DataType(Enum):
    """统一数据类型"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    JSON = "json"


@dataclass
class DataSource:
    """数据源配置"""
    id: str
    name: str
    source_type: DataSourceType
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'source_type': self.source_type.value,
            'config': self.config,
            'enabled': self.enabled,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


@dataclass
class DataRecord:
    """统一数据记录"""
    id: str
    source_id: str
    data: Dict[str, Any]
    raw_data: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'source_id': self.source_id,
            'data': self.data,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'metadata': self.metadata
        }


@dataclass
class TransformationRule:
    """数据转换规则"""
    id: str
    name: str
    source_field: str
    target_field: str
    transform_type: str
    transform_config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'source_field': self.source_field,
            'target_field': self.target_field,
            'transform_type': self.transform_type,
            'transform_config': self.transform_config,
            'enabled': self.enabled
        }


# ============================================================================
# 第二部分：数据解析器
# ============================================================================

class DataParser:
    """通用数据解析器，支持多种格式"""

    @staticmethod
    def parse_csv(content: str, delimiter: str = ',') -> List[Dict[str, Any]]:
        """解析CSV内容"""
        try:
            reader = csv.DictReader(StringIO(content), delimiter=delimiter)
            return [row for row in reader]
        except Exception as e:
            logger.error(f"CSV解析失败: {e}")
            raise

    @staticmethod
    def parse_json(content: str) -> Any:
        """解析JSON内容"""
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            raise

    @staticmethod
    def parse_xml(content: str) -> List[Dict[str, Any]]:
        """解析XML内容"""
        try:
            root = ET.fromstring(content)
            records = []
            for child in root:
                record = {}
                for elem in child:
                    record[elem.tag] = elem.text
                records.append(record)
            return records
        except ET.ParseError as e:
            logger.error(f"XML解析失败: {e}")
            raise

    @staticmethod
    def detect_format(filename: str) -> str:
        """根据文件名检测格式"""
        filename_lower = filename.lower()
        if filename_lower.endswith('.csv'):
            return 'csv'
        elif filename_lower.endswith('.json'):
            return 'json'
        elif filename_lower.endswith('.xml'):
            return 'xml'
        return 'unknown'

    @staticmethod
    def auto_parse(content: str, filename: str = None, format_hint: str = None) -> List[Dict[str, Any]]:
        """自动检测格式并解析"""
        if format_hint:
            fmt = format_hint.lower()
        elif filename:
            fmt = DataParser.detect_format(filename)
        else:
            content_stripped = content.strip()
            if content_stripped.startswith('{') or content_stripped.startswith('['):
                fmt = 'json'
            elif content_stripped.startswith('<'):
                fmt = 'xml'
            else:
                fmt = 'csv'

        if fmt == 'csv':
            return DataParser.parse_csv(content)
        elif fmt == 'json':
            result = DataParser.parse_json(content)
            return result if isinstance(result, list) else [result]
        elif fmt == 'xml':
            return DataParser.parse_xml(content)
        else:
            raise ValueError(f"不支持的格式: {fmt}")


# ============================================================================
# 第三部分：数据转换器
# ============================================================================

class DataTransformer:
    """数据转换器，将源数据转换为统一格式"""

    def __init__(self):
        self.transformations: Dict[str, Callable] = {
            'direct': self._transform_direct,
            'mapping': self._transform_mapping,
            'uppercase': self._transform_uppercase,
            'lowercase': self._transform_lowercase,
            'trim': self._transform_trim,
            'date_format': self._transform_date_format,
            'number': self._transform_number,
            'boolean': self._transform_boolean,
            'concat': self._transform_concat,
            'split': self._transform_split,
        }

    def transform_record(self, record: DataRecord, rules: List[TransformationRule]) -> Dict[str, Any]:
        """应用转换规则到数据记录"""
        result = {}
        for rule in rules:
            if not rule.enabled:
                continue
            try:
                transform_func = self.transformations.get(rule.transform_type)
                if transform_func:
                    value = record.data.get(rule.source_field)
                    result[rule.target_field] = transform_func(value, rule.transform_config)
            except Exception as e:
                logger.error(f"转换失败 - 规则: {rule.name}, 错误: {e}")
                result[rule.target_field] = rule.transform_config.get('default_value')
        return result

    def transform_records(self, records: List[DataRecord], rules: List[TransformationRule]) -> List[Dict[str, Any]]:
        """批量转换数据记录"""
        return [self.transform_record(record, rules) for record in records]

    def _transform_direct(self, value: Any, config: Dict[str, Any]) -> Any:
        return config.get('default', value) if value is None else value

    def _transform_mapping(self, value: Any, config: Dict[str, Any]) -> Any:
        return config.get('mapping', {}).get(str(value), config.get('default', value))

    def _transform_uppercase(self, value: Any, config: Dict[str, Any]) -> Any:
        return value.upper() if isinstance(value, str) else value

    def _transform_lowercase(self, value: Any, config: Dict[str, Any]) -> Any:
        return value.lower() if isinstance(value, str) else value

    def _transform_trim(self, value: Any, config: Dict[str, Any]) -> Any:
        return value.strip() if isinstance(value, str) else value

    def _transform_date_format(self, value: Any, config: Dict[str, Any]) -> Any:
        try:
            if isinstance(value, str):
                dt = datetime.strptime(value, config.get('source_format', '%Y-%m-%d'))
                return dt.strftime(config.get('target_format', '%Y-%m-%d'))
        except Exception:
            pass
        return value

    def _transform_number(self, value: Any, config: Dict[str, Any]) -> Any:
        try:
            if isinstance(value, str):
                value = value.replace(',', '').replace(' ', '')
            return float(value) if '.' in str(value) else int(value)
        except (ValueError, TypeError):
            return config.get('default', 0)

    def _transform_boolean(self, value: Any, config: Dict[str, Any]) -> Any:
        true_values = config.get('true_values', ['true', '1', 'yes', '是'])
        false_values = config.get('false_values', ['false', '0', 'no', '否'])
        if isinstance(value, str):
            value_lower = value.lower()
            if value_lower in true_values:
                return True
            elif value_lower in false_values:
                return False
        return bool(value)

    def _transform_concat(self, value: Any, config: Dict[str, Any]) -> Any:
        return config.get('separator', '').join([config.get('data', {}).get(f, '') for f in config.get('fields', [])])

    def _transform_split(self, value: Any, config: Dict[str, Any]) -> Any:
        if isinstance(value, str):
            parts = value.split(config.get('separator', ','))
            idx = config.get('index')
            return parts[idx] if idx is not None and 0 <= idx < len(parts) else parts
        return value


# ============================================================================
# 第四部分：数据源适配器基类
# ============================================================================

class BaseAdapter(ABC):
    """数据源适配器基类"""

    def __init__(self, source: DataSource):
        self.source = source
        self.connected = False

    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def disconnect(self):
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        pass

    @abstractmethod
    def fetch_data(self, query: Dict[str, Any] = None) -> Generator[Dict[str, Any], None, None]:
        pass

    @abstractmethod
    def get_schema_info(self) -> List[Dict[str, Any]]:
        pass

    def fetch_records(self, query: Dict[str, Any] = None) -> List[DataRecord]:
        """获取数据并转换为统一格式"""
        records = []
        for raw_data in self.fetch_data(query):
            record = DataRecord(
                id=self._generate_record_id(raw_data),
                source_id=self.source.id,
                data=raw_data,
                raw_data=raw_data.copy(),
                metadata={'source_type': self.source.source_type.value, 'fetch_time': datetime.now().isoformat()}
            )
            records.append(record)
        return records

    def _generate_record_id(self, data: Dict[str, Any]) -> str:
        return hashlib.md5(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


# ============================================================================
# 第五部分：SQLite数据库适配器
# ============================================================================

class DatabaseAdapter(BaseAdapter):
    """SQLite数据库适配器"""

    def __init__(self, source: DataSource):
        super().__init__(source)
        self.connection = None
        self.db_path = source.config.get('db_path', ':memory:')

    def connect(self) -> bool:
        try:
            import sqlite3
            self.connection = sqlite3.connect(self.db_path)
            self.connection.row_factory = sqlite3.Row
            self.connected = True
            return True
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            return False

    def disconnect(self):
        if self.connection:
            self.connection.close()
            self.connected = False

    def test_connection(self) -> bool:
        try:
            self.connect()
            self.connection.cursor().execute("SELECT 1")
            self.disconnect()
            return True
        except Exception:
            return False

    def fetch_data(self, query: Dict[str, Any] = None) -> Generator[Dict[str, Any], None, None]:
        if not self.connected:
            self.connect()
        if not query or 'table' not in query:
            raise ValueError("查询必须包含 'table' 参数")

        table = query['table']
        columns = ', '.join(query.get('columns', ['*']))
        conditions = query.get('conditions', {})
        limit = query.get('limit')

        sql = f"SELECT {columns} FROM {table}"
        params = []
        if conditions:
            where_clauses = [f"{k} = ?" for k in conditions.keys()]
            sql += " WHERE " + " AND ".join(where_clauses)
            params = list(conditions.values())
        if limit:
            sql += f" LIMIT {limit}"

        cursor = self.connection.cursor()
        cursor.execute(sql, params)
        for row in cursor.fetchall():
            yield dict(row)

    def get_schema_info(self) -> List[Dict[str, Any]]:
        if not self.connected:
            self.connect()
        cursor = self.connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        schema_info = []
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table['name']})")
            columns = cursor.fetchall()
            schema_info.append({
                'table': table['name'],
                'columns': [{'name': c['name'], 'type': c['type']} for c in columns]
            })
        return schema_info


# ============================================================================
# 第六部分：文件适配器
# ============================================================================

class FileAdapter(BaseAdapter):
    """文件适配器，支持CSV/JSON/XML"""

    def __init__(self, source: DataSource):
        super().__init__(source)
        self.file_path = source.config.get('file_path', '')
        self.encoding = source.config.get('encoding', 'utf-8')

    def connect(self) -> bool:
        if not os.path.exists(self.file_path):
            logger.error(f"文件不存在: {self.file_path}")
            return False
        self.connected = True
        return True

    def disconnect(self):
        self.connected = False

    def test_connection(self) -> bool:
        try:
            with open(self.file_path, 'r', encoding=self.encoding) as f:
                f.read(1024)
            return True
        except Exception:
            return False

    def fetch_data(self, query: Dict[str, Any] = None) -> Generator[Dict[str, Any], None, None]:
        if not self.connected:
            self.connect()
        with open(self.file_path, 'r', encoding=self.encoding) as f:
            content = f.read()
        filename = os.path.basename(self.file_path)
        data = DataParser.auto_parse(content, filename)
        for item in data:
            yield item

    def get_schema_info(self) -> List[Dict[str, Any]]:
        try:
            with open(self.file_path, 'r', encoding=self.encoding) as f:
                lines = [f.readline() for _ in range(5)]
            filename = os.path.basename(self.file_path)
            fmt = DataParser.detect_format(filename)
            if fmt == 'csv':
                reader = csv.DictReader(lines)
                if reader.fieldnames:
                    return [{'columns': [{'name': col, 'type': 'string'} for col in reader.fieldnames]}]
            return []
        except Exception:
            return []


# ============================================================================
# 第七部分：数据管理器
# ============================================================================

class DataManager:
    """数据管理器，协调整个数据处理流程"""

    def __init__(self, storage_path: str = "./data"):
        self.storage_path = storage_path
        self.data_sources: Dict[str, DataSource] = {}
        self.adapters: Dict[DataSourceType, Type[BaseAdapter]] = {}
        self.transformation_rules: Dict[str, List[TransformationRule]] = {}
        self.transformer = DataTransformer()
        os.makedirs(storage_path, exist_ok=True)
        self._load_state()

    def register_adapter(self, source_type: DataSourceType, adapter_class: Type[BaseAdapter]):
        self.adapters[source_type] = adapter_class

    def add_data_source(self, source: DataSource) -> bool:
        try:
            self.data_sources[source.id] = source
            self._save_state()
            return True
        except Exception as e:
            logger.error(f"添加数据源失败: {e}")
            return False

    def remove_data_source(self, source_id: str) -> bool:
        if source_id in self.data_sources:
            del self.data_sources[source_id]
            self._save_state()
            return True
        return False

    def list_data_sources(self) -> List[DataSource]:
        return list(self.data_sources.values())

    def fetch_data(self, source_id: str, query: Dict[str, Any] = None) -> List[DataRecord]:
        source = self.data_sources.get(source_id)
        if not source:
            raise ValueError(f"数据源不存在: {source_id}")
        adapter_class = self.adapters.get(source.source_type)
        if not adapter_class:
            raise ValueError(f"未找到适配器: {source.source_type}")
        adapter = adapter_class(source)
        try:
            adapter.connect()
            return adapter.fetch_records(query)
        finally:
            adapter.disconnect()

    def import_file(self, content: str, filename: str, source_id: str = None) -> List[DataRecord]:
        parsed_data = DataParser.auto_parse(content, filename)
        return [
            DataRecord(
                id=str(uuid.uuid4()),
                source_id=source_id or "file_import",
                data=data,
                raw_data=data.copy(),
                metadata={'source_type': 'file', 'filename': filename, 'import_time': datetime.now().isoformat()}
            )
            for data in parsed_data
        ]

    def transform_data(self, records: List[DataRecord], schema_id: str) -> List[Dict[str, Any]]:
        rules = self.transformation_rules.get(schema_id, [])
        return self.transformer.transform_records(records, rules)

    def add_transformation_rule(self, schema_id: str, rule: TransformationRule):
        if schema_id not in self.transformation_rules:
            self.transformation_rules[schema_id] = []
        self.transformation_rules[schema_id].append(rule)
        self._save_state()

    def _save_state(self):
        state = {
            'data_sources': {k: v.to_dict() for k, v in self.data_sources.items()},
            'transformation_rules': {k: [r.to_dict() for r in v] for k, v in self.transformation_rules.items()}
        }
        with open(os.path.join(self.storage_path, 'state.json'), 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def _load_state(self):
        state_file = os.path.join(self.storage_path, 'state.json')
        if not os.path.exists(state_file):
            return
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            for k, v in state.get('data_sources', {}).items():
                self.data_sources[k] = DataSource(
                    id=v['id'], name=v['name'],
                    source_type=DataSourceType(v['source_type']),
                    config=v.get('config', {}), enabled=v.get('enabled', True)
                )
            for schema_id, rules in state.get('transformation_rules', {}).items():
                self.transformation_rules[schema_id] = [
                    TransformationRule(**{kk: rr[kk] for kk in ['id', 'name', 'source_field', 'target_field', 'transform_type']})
                    | {'transform_config': rr.get('transform_config', {}), 'enabled': rr.get('enabled', True)}
                    for rr in rules
                ]
        except Exception as e:
            logger.error(f"加载状态失败: {e}")


# ============================================================================
# 第八部分：Web界面HTML模板
# ============================================================================

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>数据集成系统</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Microsoft YaHei', sans-serif; background: #f5f7fa; color: #333; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; margin-bottom: 30px; }
        header h1 { font-size: 28px; }
        .card { background: white; border-radius: 10px; padding: 25px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        .card h2 { color: #667eea; margin-bottom: 15px; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: 500; }
        .form-group input, .form-group select { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; }
        .btn { padding: 10px 20px; border: none; border-radius: 6px; cursor: pointer; margin-right: 10px; }
        .btn-primary { background: #667eea; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        .source-item { display: flex; justify-content: space-between; align-items: center; padding: 15px; background: #f8f9fa; border-radius: 8px; margin-bottom: 10px; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #667eea; color: white; }
    </style>
</head>
<body>
    <div class="container">
        <header><h1>数据集成系统</h1><p>提取、解析并整合多源数据</p></header>
        <div class="card">
            <h2>添加数据源</h2>
            <form id="addForm">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                    <div class="form-group"><label>名称</label><input type="text" id="name" required></div>
                    <div class="form-group"><label>类型</label><select id="type"><option value="file_csv">CSV文件</option><option value="file_json">JSON文件</option><option value="file_xml">XML文件</option><option value="database">SQLite数据库</option></select></div>
                    <div class="form-group"><label>文件路径</label><input type="text" id="path" placeholder="./data.csv"></div>
                </div>
                <button type="submit" class="btn btn-primary">添加</button>
            </form>
        </div>
        <div class="card"><h2>数据源列表</h2><div id="list"></div></div>
        <div class="card"><h2>数据预览</h2><div id="preview"></div></div>
    </div>
    <script>
        let sources = [];
        document.getElementById('addForm').onsubmit = async (e) => {
            e.preventDefault();
            const s = { id: Date.now().toString(), name: document.getElementById('name').value, source_type: document.getElementById('type').value, config: { file_path: document.getElementById('path').value, encoding: 'utf-8' } };
            sources.push(s); render(); alert('已添加');
        };
        function render() {
            document.getElementById('list').innerHTML = sources.map(s => `<div class="source-item"><div><b>${s.name}</b><br><small>${s.source_type}</small></div><button class="btn btn-danger" onclick="sources=sources.filter(x=>x.id!==\\'${s.id}\\');render()">删除</button></div>`).join('');
        }
    </script>
</body>
</html>'''


# ============================================================================
# 第九部分：Flask Web应用（可选）
# ============================================================================

def create_flask_app():
    """创建Flask Web应用"""
    try:
        from flask import Flask, render_template_string, request, jsonify
        from flask_cors import CORS

        app = Flask(__name__)
        CORS(app)

        manager = DataManager()
        manager.register_adapter(DataSourceType.DATABASE, DatabaseAdapter)
        manager.register_adapter(DataSourceType.FILE_CSV, FileAdapter)
        manager.register_adapter(DataSourceType.FILE_JSON, FileAdapter)
        manager.register_adapter(DataSourceType.FILE_XML, FileAdapter)

        @app.route('/')
        def index():
            return render_template_string(HTML_TEMPLATE)

        @app.route('/api/sources', methods=['GET'])
        def list_sources():
            return jsonify([s.to_dict() for s in manager.list_data_sources()])

        @app.route('/api/sources', methods=['POST'])
        def add_source():
            data = request.json
            source = DataSource(id=data['id'], name=data['name'], source_type=DataSourceType(data['source_type']), config=data.get('config', {}))
            return jsonify({'success': manager.add_data_source(source)})

        @app.route('/api/sources/<source_id>', methods=['DELETE'])
        def delete_source(source_id):
            return jsonify({'success': manager.remove_data_source(source_id)})

        @app.route('/api/sources/<source_id>/fetch', methods=['POST'])
        def fetch_data(source_id):
            try:
                records = manager.fetch_data(source_id, request.json)
                return jsonify({'success': True, 'data': [r.to_dict() for r in records]})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 400

        @app.route('/api/import/file', methods=['POST'])
        def import_file():
            if 'file' not in request.files:
                return jsonify({'error': '没有文件'}), 400
            file = request.files['file']
            content = file.read().decode('utf-8')
            records = manager.import_file(content, file.filename)
            return jsonify({'success': True, 'count': len(records), 'data': [r.to_dict() for r in records]})

        return app
    except ImportError:
        logger.warning("Flask未安装，Web界面不可用。请运行: pip install flask flask-cors")
        return None


# ============================================================================
# 第十部分：命令行界面
# ============================================================================

def run_cli():
    """运行命令行界面"""
    manager = DataManager()
    manager.register_adapter(DataSourceType.DATABASE, DatabaseAdapter)
    manager.register_adapter(DataSourceType.FILE_CSV, FileAdapter)
    manager.register_adapter(DataSourceType.FILE_JSON, FileAdapter)
    manager.register_adapter(DataSourceType.FILE_XML, FileAdapter)

    print("\n" + "=" * 50)
    print("数据集成系统 - 命令行模式")
    print("=" * 50)
    print("命令:")
    print("  1. list     - 列出数据源")
    print("  2. import   - 导入文件")
    print("  3. fetch    - 获取数据")
    print("  4. demo     - 运行演示")
    print("  5. web      - 启动Web服务")
    print("  6. quit     - 退出")
    print("=" * 50)

    while True:
        cmd = input("\n请输入命令: ").strip().lower()

        if cmd == '1' or cmd == 'list':
            sources = manager.list_data_sources()
            if not sources:
                print("暂无数据源")
            for s in sources:
                print(f"  - {s.name} ({s.source_type.value})")

        elif cmd == '2' or cmd == 'import':
            path = input("请输入文件路径: ").strip()
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                records = manager.import_file(content, os.path.basename(path))
                print(f"成功导入 {len(records)} 条记录")
                for r in records[:3]:
                    print(f"  {r.data}")
            else:
                print("文件不存在")

        elif cmd == '4' or cmd == 'demo':
            run_demo(manager)

        elif cmd == '5' or cmd == 'web':
            app = create_flask_app()
            if app:
                print("\n启动Web服务: http://localhost:5000")
                app.run(debug=False, port=5000)
            else:
                print("请先安装Flask: pip install flask flask-cors")

        elif cmd == '6' or cmd == 'quit':
            print("再见!")
            break


def run_demo(manager: DataManager = None):
    """运行演示"""
    if manager is None:
        manager = DataManager()
        manager.register_adapter(DataSourceType.FILE_CSV, FileAdapter)
        manager.register_adapter(DataSourceType.FILE_JSON, FileAdapter)
        manager.register_adapter(DataSourceType.FILE_XML, FileAdapter)

    print("\n" + "=" * 50)
    print("演示: 数据解析和转换")
    print("=" * 50)

    # 演示CSV解析
    csv_content = "姓名,年龄,部门\n张三,28,技术部\n李四,32,市场部"
    print("\n1. CSV解析:")
    records = manager.import_file(csv_content, "test.csv")
    for r in records:
        print(f"   {r.data}")

    # 演示JSON解析
    json_content = '[{"name": "产品A", "price": 99.99}, {"name": "产品B", "price": 49.99}]'
    print("\n2. JSON解析:")
    records = manager.import_file(json_content, "test.json")
    for r in records:
        print(f"   {r.data}")

    # 演示转换
    print("\n3. 数据转换:")
    rule = TransformationRule(id="1", name="姓名转大写", source_field="姓名", target_field="name_upper", transform_type="uppercase")
    manager.add_transformation_rule("demo", rule)
    transformed = manager.transform_data(records, "demo")
    for t in transformed:
        print(f"   {t}")

    print("\n" + "=" * 50)
    print("演示完成!")
    print("=" * 50)


# ============================================================================
# 主程序入口
# ============================================================================

if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════════╗
║                    第一次试验 - 数据集成系统                    ║
║                                                               ║
║  功能: 提取、解析并整合多源数据到统一格式                         ║
║  版本: 1.0                                                    ║
║  依赖: Python 3.8+ (可选: pip install flask flask-cors)       ║
╚═══════════════════════════════════════════════════════════════╝
    """)

    if len(sys.argv) > 1:
        if sys.argv[1] == '--web':
            app = create_flask_app()
            if app:
                app.run(host='0.0.0.0', port=5000)
        elif sys.argv[1] == '--demo':
            run_demo()
        elif sys.argv[1] == '--help':
            print("用法: python 第一次试验.py [选项]")
            print("  无参数   - 命令行交互模式")
            print("  --web    - 启动Web服务")
            print("  --demo   - 运行演示")
            print("  --help   - 显示帮助")
        else:
            print(f"未知选项: {sys.argv[1]}")
    else:
        run_cli()