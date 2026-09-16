import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  TextField,
  InputAdornment,
  Grid,
  Alert,
  CircularProgress,
  IconButton,
  Badge,
  Tabs,
  Tab,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material';
import {
  Search as SearchIcon,
  Inventory as InventoryIcon,
  Warning as WarningIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { inventoryAPI, InventoryItem } from '../services/inventoryAPI';
import { TabPanel } from '../components/common';
import { formatZhDate, translateWarehouseLocation } from '../localization/zhCN';

const InventoryPage: React.FC = () => {
  const [inventoryItems, setInventoryItems] = useState<InventoryItem[]>([]);
  const [filteredItems, setFilteredItems] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [brandFilter, setBrandFilter] = useState('all');
  const [tabValue, setTabValue] = useState(0);
  const [brands, setBrands] = useState<string[]>(['all']);

  useEffect(() => {
    fetchInventoryItems();
  }, []);

  const filterItems = useCallback(() => {
    let filtered = inventoryItems;

    // Filter by search term
    if (searchTerm) {
      filtered = filtered.filter(item =>
        item.sku.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.location.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    // Filter by brand
    if (brandFilter !== 'all') {
      filtered = filtered.filter(item => item.sku.startsWith(brandFilter));
    }

    setFilteredItems(filtered);
  }, [inventoryItems, searchTerm, brandFilter]);

  useEffect(() => {
    filterItems();
  }, [filterItems]);

  const fetchInventoryItems = async () => {
    try {
      setLoading(true);
      setError(null);
      const items = await inventoryAPI.getAllItems();
      setInventoryItems(items);
      
      // Dynamically extract brands from actual SKUs
      const uniqueBrands = new Set<string>(['all']);
      items.forEach(item => {
        // Extract brand prefix (first 3 characters of SKU)
        if (item.sku && item.sku.length >= 3) {
          const brandPrefix = item.sku.substring(0, 3).toUpperCase();
          uniqueBrands.add(brandPrefix);
        }
      });
      setBrands(Array.from(uniqueBrands).sort((a, b) => a.localeCompare(b)));
    } catch (err) {
      setError('库存数据获取失败');
      // console.error('Error fetching inventory items:', err);
    } finally {
      setLoading(false);
    }
  };

  const getLowStockItems = () => {
    return inventoryItems.filter(item => item.quantity < item.reorder_point);
  };

  const getBrandItems = (brand: string) => {
    return inventoryItems.filter(item => item.sku.startsWith(brand));
  };

  const getStockStatus = (item: InventoryItem) => {
    if (item.quantity === 0) return { status: '缺货', color: 'error' as const };
    if (item.quantity < item.reorder_point) return { status: '低库存', color: 'warning' as const };
    if (item.quantity < item.reorder_point * 1.5) return { status: '库存中等', color: 'info' as const };
    return { status: '库存充足', color: 'success' as const };
  };

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Box p={3}>
        <Alert severity="error" action={
          <IconButton aria-label="重新加载库存" color="inherit" size="small" onClick={fetchInventoryItems}>
            <RefreshIcon />
          </IconButton>
        }>
          {error}
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" component="h1" gutterBottom>
          <InventoryIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
          库存管理
        </Typography>
        <IconButton aria-label="刷新库存" onClick={fetchInventoryItems} color="primary">
          <RefreshIcon />
        </IconButton>
      </Box>

      {/* Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                产品总数
              </Typography>
              <Typography variant="h4">
                {inventoryItems.length}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                低库存产品
              </Typography>
              <Typography variant="h4" color="warning.main">
                <Badge badgeContent={getLowStockItems().length} color="warning">
                  <WarningIcon />
                </Badge>
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                库存总值
              </Typography>
              <Typography variant="h4">
                暂无
              </Typography>
              <Typography variant="caption" color="text.secondary">
                暂无成本数据
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                品牌数
              </Typography>
              <Typography variant="h4">
                {brands.length - 1}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Filters */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} sm={6} md={4}>
              <TextField
                fullWidth
                placeholder="搜索产品..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon />
                    </InputAdornment>
                  ),
                }}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={4}>
              <FormControl fullWidth>
                <InputLabel>品牌</InputLabel>
                <Select
                  value={brandFilter}
                  label="品牌"
                  onChange={(e) => setBrandFilter(e.target.value)}
                >
                  {brands.map((brand) => (
                    <MenuItem key={brand} value={brand}>
                      {brand === 'all' ? '全部品牌' : brand}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={12} md={4}>
              <Typography variant="body2" color="textSecondary">
                共 {inventoryItems.length} 个产品，当前显示 {filteredItems.length} 个
              </Typography>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Tabs value={tabValue} onChange={handleTabChange} aria-label="库存分类标签页">
          <Tab label="全部产品" />
          <Tab 
            label={
              <Badge badgeContent={getLowStockItems().length} color="warning">
                低库存
              </Badge>
            } 
          />
          <Tab label="Lay's" />
          <Tab label="Doritos" />
          <Tab label="Cheetos" />
        </Tabs>
      </Box>

      {/* All Products Tab */}
      <TabPanel value={tabValue} index={0} idPrefix="inventory">
        <InventoryTable items={filteredItems} />
      </TabPanel>

      {/* Low Stock Tab */}
      <TabPanel value={tabValue} index={1} idPrefix="inventory">
        <InventoryTable items={getLowStockItems()} />
      </TabPanel>

      {/* Brand Tabs */}
      <TabPanel value={tabValue} index={2} idPrefix="inventory">
        <InventoryTable items={getBrandItems('LAY')} />
      </TabPanel>

      <TabPanel value={tabValue} index={3} idPrefix="inventory">
        <InventoryTable items={getBrandItems('DOR')} />
      </TabPanel>

      <TabPanel value={tabValue} index={4} idPrefix="inventory">
        <InventoryTable items={getBrandItems('CHE')} />
      </TabPanel>
    </Box>
  );
};

interface InventoryTableProps {
  items: InventoryItem[];
}

const InventoryTable: React.FC<Readonly<InventoryTableProps>> = ({ items }) => {
  const getStockStatus = (item: InventoryItem) => {
    if (item.quantity === 0) return { status: '缺货', color: 'error' as const };
    if (item.quantity < item.reorder_point) return { status: '低库存', color: 'warning' as const };
    if (item.quantity < item.reorder_point * 1.5) return { status: '库存中等', color: 'info' as const };
    return { status: '库存充足', color: 'success' as const };
  };

  if (items.length === 0) {
    return (
      <Alert severity="info">
        未找到符合当前筛选条件的库存产品。
      </Alert>
    );
  }

  return (
    <TableContainer component={Paper}>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>SKU</TableCell>
            <TableCell>产品名称</TableCell>
            <TableCell>数量</TableCell>
            <TableCell>库位</TableCell>
            <TableCell>补货点</TableCell>
            <TableCell>状态</TableCell>
            <TableCell>最后更新</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {items.map((item) => {
            const stockStatus = getStockStatus(item);
            return (
              <TableRow key={item.sku} hover>
                <TableCell>
                  <Typography variant="body2" fontWeight="bold">
                    {item.sku}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2">
                    {item.name}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" fontWeight="bold">
                    {item.quantity.toLocaleString()}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" color="textSecondary">
                    {translateWarehouseLocation(item.location)}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2">
                    {item.reorder_point}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip
                    label={stockStatus.status}
                    color={stockStatus.color}
                    size="small"
                  />
                </TableCell>
                <TableCell>
                  <Typography variant="body2" color="textSecondary">
                    {formatZhDate(item.updated_at)}
                  </Typography>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
};


export default InventoryPage;
