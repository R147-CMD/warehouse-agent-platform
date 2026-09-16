import React, { useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Grid,
  Chip,
  Alert,
  Card,
  CardContent,
  Tabs,
  Tab,
  List,
  ListItem,
  ListItemText,
  IconButton,
  Tooltip,
  CircularProgress,
  Drawer,
  Divider,
  LinearProgress,
  Stack,
} from '@mui/material';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import { zhCN as dataGridZhCN } from '@mui/x-data-grid/locales';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Assignment as AssignmentIcon,
  Build as BuildIcon,
  Security as SecurityIcon,
  TrendingUp as TrendingUpIcon,
  Visibility as VisibilityIcon,
  Close as CloseIcon,
  CalendarToday as CalendarIcon,
  Factory as FactoryIcon,
  Settings as SettingsIcon,
  BatteryChargingFull as BatteryIcon,
  Speed as SpeedIcon,
  LocationOn as LocationIcon,
  Person as PersonIcon,
  CheckCircle as CheckCircleIcon,
  Warning as WarningIcon,
  Info as InfoIcon,
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer } from 'recharts';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { equipmentAPI, EquipmentAsset } from '../services/api';
import { TabPanel } from '../components/common';
import {
  formatZhDate,
  formatZhDateTime,
  translateAssignmentType,
  translateAssetType,
  translatePriority,
  translateStatus,
  translateWarehouseLocation,
} from '../localization/zhCN';

const formatAssetType = (type: string) =>
  type === 'charger' ? '充电器' : translateAssetType(type);

const maintenanceTypeLabels: Readonly<Record<string, string>> = {
  preventive: '预防性维护',
  corrective: '纠正性维护',
  emergency: '紧急维护',
  inspection: '检查',
};

const translateMaintenanceType = (type: string) => maintenanceTypeLabels[type.toLowerCase()] || type;

const EquipmentNew: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [selectedAsset, setSelectedAsset] = useState<EquipmentAsset | null>(null);
  const [formData, setFormData] = useState<Partial<EquipmentAsset>>({});
  const [activeTab, setActiveTab] = useState(0);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerAssetId, setDrawerAssetId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: equipmentAssets, isLoading, error } = useQuery({
    queryKey: ['equipment'],
    queryFn: equipmentAPI.getAllAssets
  });

  const { data: assignments } = useQuery({
    queryKey: ['equipment-assignments'],
    queryFn: () => equipmentAPI.getAssignments(undefined, undefined, true),
    enabled: activeTab === 1
  });

  const { data: maintenanceSchedule } = useQuery({
    queryKey: ['equipment-maintenance'],
    queryFn: () => equipmentAPI.getMaintenanceSchedule(undefined, undefined, 30),
    enabled: activeTab === 2
  });

  const { data: telemetryData, isLoading: telemetryLoading } = useQuery({
    queryKey: ['equipment-telemetry', selectedAssetId],
    queryFn: () => selectedAssetId ? equipmentAPI.getTelemetry(selectedAssetId, undefined, 168) : [],
    enabled: !!selectedAssetId && activeTab === 3
  });

  // Fetch detailed asset data for drawer
  const { data: drawerAsset, isLoading: drawerAssetLoading } = useQuery({
    queryKey: ['equipment-asset-detail', drawerAssetId],
    queryFn: () => drawerAssetId ? equipmentAPI.getAsset(drawerAssetId) : null,
    enabled: !!drawerAssetId
  });

  // Fetch telemetry for drawer
  const { data: drawerTelemetryRaw, isLoading: drawerTelemetryLoading } = useQuery({
    queryKey: ['equipment-telemetry-drawer', drawerAssetId],
    queryFn: () => drawerAssetId ? equipmentAPI.getTelemetry(drawerAssetId, undefined, 168) : [],
    enabled: !!drawerAssetId && drawerOpen
  });

  // Transform telemetry data for chart
  const drawerTelemetry = React.useMemo(() => {
    if (!drawerTelemetryRaw || !Array.isArray(drawerTelemetryRaw) || drawerTelemetryRaw.length === 0) return [];
    
    // Group by timestamp and aggregate metrics
    const grouped: Record<string, Record<string, any>> = {};
    drawerTelemetryRaw.forEach((item: any) => {
      const timestamp = item.timestamp || item.ts;
      if (!timestamp) return;
      
      const timeKey = new Date(timestamp).toISOString();
      if (!grouped[timeKey]) {
        grouped[timeKey] = { timestamp: new Date(timestamp).getTime(), timeLabel: formatZhDateTime(timestamp) };
      }
      const metricName = item.metric || 'value';
      grouped[timeKey][metricName] = item.value;
    });
    
    return Object.values(grouped).sort((a: any, b: any) => a.timestamp - b.timestamp);
  }, [drawerTelemetryRaw]);

  // Get unique metrics for chart lines
  const telemetryMetrics = React.useMemo(() => {
    if (!drawerTelemetryRaw || !Array.isArray(drawerTelemetryRaw)) return [];
    return Array.from(new Set(drawerTelemetryRaw.map((item: any) => item.metric).filter(Boolean)));
  }, [drawerTelemetryRaw]);

  // Fetch maintenance schedule for drawer
  const { data: drawerMaintenance, isLoading: drawerMaintenanceLoading } = useQuery({
    queryKey: ['equipment-maintenance-drawer', drawerAssetId],
    queryFn: () => drawerAssetId ? equipmentAPI.getMaintenanceSchedule(drawerAssetId, undefined, 90) : [],
    enabled: !!drawerAssetId && drawerOpen
  });

  const assignMutation = useMutation({
    mutationFn: equipmentAPI.assignAsset,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['equipment-assignments'] });
      setOpen(false);
    },
  });

  const releaseMutation = useMutation({
    mutationFn: equipmentAPI.releaseAsset,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['equipment-assignments'] });
      queryClient.invalidateQueries({ queryKey: ['equipment'] });
    },
  });

  const maintenanceMutation = useMutation({
    mutationFn: equipmentAPI.scheduleMaintenance,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['equipment-maintenance'] });
      setOpen(false);
    },
  });

  const handleOpen = (asset?: EquipmentAsset) => {
    if (asset) {
      setSelectedAsset(asset);
      setFormData(asset);
    } else {
      setSelectedAsset(null);
      setFormData({});
    }
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
    setSelectedAsset(null);
    setFormData({});
  };

  const handleAssign = () => {
    if (selectedAsset) {
      assignMutation.mutate({
        asset_id: selectedAsset.asset_id,
        assignee: formData.owner_user || 'system',
        assignment_type: 'task',
        notes: '从界面手动分配',
      });
    }
  };

  const handleRelease = (assetId: string) => {
    releaseMutation.mutate({
      asset_id: assetId,
      released_by: 'system',
      notes: '从界面手动释放',
    });
  };

  const handleScheduleMaintenance = () => {
    if (selectedAsset) {
      maintenanceMutation.mutate({
        asset_id: selectedAsset.asset_id,
        maintenance_type: 'preventive',
        description: formData.metadata?.maintenance_description || '计划维护',
        scheduled_by: 'system',
        scheduled_for: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
        estimated_duration_minutes: 60,
        priority: 'medium',
      });
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'available': return 'success';
      case 'assigned': return 'info';
      case 'charging': return 'warning';
      case 'maintenance': return 'error';
      case 'out_of_service': return 'error';
      default: return 'default';
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'forklift': return '🚛';
      case 'amr': return '🤖';
      case 'agv': return '🚚';
      case 'scanner': return '📱';
      case 'charger': return '🔌';
      case 'conveyor': return '📦';
      case 'humanoid': return '👤';
      default: return '⚙️';
    }
  };

  const handleAssetClick = (assetId: string) => {
    setDrawerAssetId(assetId);
    setDrawerOpen(true);
  };

  const handleDrawerClose = () => {
    setDrawerOpen(false);
    setDrawerAssetId(null);
  };

  const columns: GridColDef[] = [
    { 
      field: 'asset_id', 
      headerName: '资产 ID', 
      width: 150,
      renderCell: (params) => (
        <Box 
          sx={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: 1,
            cursor: 'pointer',
            '&:hover': {
              textDecoration: 'underline',
              color: 'primary.main',
            }
          }}
          onClick={() => handleAssetClick(params.value)}
        >
          <span>{getTypeIcon(params.row.type)}</span>
          <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
            {params.value}
          </Typography>
        </Box>
      ),
    },
    {
      field: 'type',
      headerName: '类型',
      width: 120,
      renderCell: (params) => formatAssetType(params.value),
    },
    { field: 'model', headerName: '型号', flex: 1, minWidth: 200 },
    {
      field: 'zone',
      headerName: '区域',
      width: 120,
      renderCell: (params) => translateWarehouseLocation(params.value),
    },
    {
      field: 'status',
      headerName: '状态',
      width: 140,
      renderCell: (params) => (
        <Chip
          label={translateStatus(params.value)}
          color={getStatusColor(params.value) as any}
          size="small"
        />
      ),
    },
    { field: 'owner_user', headerName: '已分配给', flex: 1, minWidth: 150 },
    {
      field: 'next_pm_due',
      headerName: '下次预防性维护',
      width: 140,
      renderCell: (params) => 
        params.value ? formatZhDate(params.value) : '暂无',
    },
    {
      field: 'actions',
      headerName: '操作',
      width: 150,
      renderCell: (params) => (
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Tooltip title="查看详情">
            <IconButton
              aria-label="查看资产详情"
              size="small"
              onClick={() => {
                setSelectedAssetId(params.row.asset_id);
                setActiveTab(3);
              }}
            >
              <VisibilityIcon />
            </IconButton>
          </Tooltip>
          <Tooltip title="编辑">
            <IconButton
              aria-label="编辑资产"
              size="small"
              onClick={() => handleOpen(params.row)}
            >
              <EditIcon />
            </IconButton>
          </Tooltip>
        </Box>
      ),
    },
  ];

  if (error) {
    return (
      <Box>
        <Typography variant="h4" gutterBottom>
          设备与资产运营
        </Typography>
        <Alert severity="error">
          设备数据加载失败，请重试。
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ width: '100%', maxWidth: 'none', p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" gutterBottom>
          设备与资产运营
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => handleOpen()}
          sx={{ backgroundColor: '#76B900', '&:hover': { backgroundColor: '#5a8f00' } }}
        >
          添加资产
        </Button>
      </Box>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs
          value={activeTab}
          onChange={(_, newValue) => {
            setActiveTab(newValue);
            // Auto-select first asset when switching to Telemetry tab if none selected
            if (newValue === 3 && !selectedAssetId && equipmentAssets && equipmentAssets.length > 0) {
              setSelectedAssetId(equipmentAssets[0].asset_id);
            }
          }}
        >
          <Tab label="资产" icon={<BuildIcon />} />
          <Tab label="分配" icon={<AssignmentIcon />} />
          <Tab label="维护" icon={<SecurityIcon />} />
          <Tab label="遥测" icon={<TrendingUpIcon />} />
        </Tabs>
      </Box>

      {/* Assets Tab */}
      <TabPanel value={activeTab} index={0} idPrefix="equipment" fullWidth>
        <Paper sx={{ height: 600, width: '100%' }}>
          <DataGrid
            rows={equipmentAssets || []}
            columns={columns}
            localeText={dataGridZhCN.components.MuiDataGrid.defaultProps.localeText}
            loading={isLoading}
            initialState={{
              pagination: {
                paginationModel: { pageSize: 10 },
              },
            }}
            pageSizeOptions={[10, 25, 50]}
            disableRowSelectionOnClick
            getRowId={(row) => row.asset_id}
            sx={{
              border: 'none',
              '& .MuiDataGrid-cell': {
                borderBottom: '1px solid #f0f0f0',
              },
              '& .MuiDataGrid-row': {
                minHeight: '48px !important',
              },
              '& .MuiDataGrid-columnHeaders': {
                backgroundColor: '#f5f5f5',
                fontWeight: 'bold',
              },
            }}
          />
        </Paper>
      </TabPanel>

      {/* Assignments Tab */}
      <TabPanel value={activeTab} index={1} idPrefix="equipment" fullWidth>
        <Paper sx={{ p: 2, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            当前分配
          </Typography>
          {assignments && assignments.length > 0 ? (
            <List>
              {assignments.map((assignment: any) => (
                <Card key={assignment.id} sx={{ mb: 2 }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Box>
                        <Typography variant="h6">
                          {assignment.asset_id}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          分配给：{assignment.assignee}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          类型：{translateAssignmentType(assignment.assignment_type)}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          分配时间：{formatZhDateTime(assignment.assigned_at)}
                        </Typography>
                      </Box>
                      <Button
                        variant="outlined"
                        color="error"
                        onClick={() => handleRelease(assignment.asset_id)}
                      >
                        释放
                      </Button>
                    </Box>
                  </CardContent>
                </Card>
              ))}
            </List>
          ) : (
            <Typography variant="body2" color="text.secondary">
              暂无当前分配
            </Typography>
          )}
        </Paper>
      </TabPanel>

      {/* Maintenance Tab */}
      <TabPanel value={activeTab} index={2} idPrefix="equipment" fullWidth>
        <Paper sx={{ p: 2, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            维护计划
          </Typography>
          {maintenanceSchedule && maintenanceSchedule.length > 0 ? (
            <List>
              {maintenanceSchedule.map((maintenance: any) => (
                <Card key={maintenance.id} sx={{ mb: 2 }}>
                  <CardContent>
                    <Typography variant="h6">
                      {maintenance.asset_id} - {translateMaintenanceType(maintenance.maintenance_type)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {maintenance.description}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      计划时间：{formatZhDateTime(maintenance.performed_at)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      持续时间：{maintenance.duration_minutes} 分钟
                    </Typography>
                  </CardContent>
                </Card>
              ))}
            </List>
          ) : (
            <Typography variant="body2" color="text.secondary">
              暂无已计划的维护
            </Typography>
          )}
        </Paper>
      </TabPanel>

      {/* Telemetry Tab */}
      <TabPanel value={activeTab} index={3} idPrefix="equipment" fullWidth>
        <Paper sx={{ p: 2, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            设备遥测
          </Typography>
          {equipmentAssets && equipmentAssets.length > 0 ? (
            <Box>
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  选择资产以查看遥测数据：
                </Typography>
                <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 2 }}>
                  {equipmentAssets.map((asset) => (
                    <Chip
                      key={asset.asset_id}
                      label={`${asset.asset_id} (${formatAssetType(asset.type)})`}
                      onClick={() => setSelectedAssetId(asset.asset_id)}
                      color={selectedAssetId === asset.asset_id ? 'primary' : 'default'}
                      variant={selectedAssetId === asset.asset_id ? 'filled' : 'outlined'}
                      sx={{ cursor: 'pointer' }}
                    />
                  ))}
                </Box>
              </Box>
              {selectedAssetId ? (
                <Box>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    资产：{selectedAssetId}
                  </Typography>
                  {telemetryLoading ? (
                    <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
                      <CircularProgress />
                    </Box>
                  ) : telemetryData && telemetryData.length > 0 ? (
                    <List>
                      {telemetryData.map((data: any, index: number) => (
                        <ListItem key={index}>
                          <ListItemText
                            primary={`${data.metric}: ${data.value} ${data.unit || ''}`}
                            secondary={`${formatZhDateTime(data.timestamp)}${data.quality_score ? `（质量：${(data.quality_score * 100).toFixed(1)}%）` : ''}`}
                          />
                        </ListItem>
                      ))}
                    </List>
                  ) : (
                    <Alert severity="info" sx={{ mt: 2 }}>
                      {selectedAssetId} 过去 7 天内暂无遥测数据。
                      <Typography variant="body2" sx={{ mt: 1 }}>
                        遥测数据可能尚未生成，或该资产近期没有遥测记录。
                      </Typography>
                    </Alert>
                  )}
                </Box>
              ) : (
                <Alert severity="info">
                  请从上方列表中选择资产以查看遥测数据。
                </Alert>
              )}
            </Box>
          ) : (
            <Typography variant="body2" color="text.secondary">
              暂无可用设备资产
            </Typography>
          )}
        </Paper>
      </TabPanel>

      {/* Asset Details Dialog */}
      <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
        <DialogTitle>
          {selectedAsset ? '编辑资产' : '添加新资产'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="资产 ID"
                value={formData.asset_id || ''}
                onChange={(e) => setFormData({ ...formData, asset_id: e.target.value })}
                disabled={!!selectedAsset}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="类型"
                value={formData.type || ''}
                onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                select
                SelectProps={{ native: true }}
              >
                <option value="">选择类型</option>
                <option value="forklift">叉车</option>
                <option value="amr">AMR</option>
                <option value="agv">AGV</option>
                <option value="scanner">扫描器</option>
                <option value="charger">充电器</option>
                <option value="conveyor">输送机</option>
                <option value="humanoid">人形机器人</option>
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="型号"
                value={formData.model || ''}
                onChange={(e) => setFormData({ ...formData, model: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="区域"
                value={formData.zone || ''}
                onChange={(e) => setFormData({ ...formData, zone: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="状态"
                value={formData.status || ''}
                onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                select
                SelectProps={{ native: true }}
              >
                <option value="">选择状态</option>
                <option value="available">可用</option>
                <option value="assigned">已分配</option>
                <option value="charging">充电中</option>
                <option value="maintenance">维护中</option>
                <option value="out_of_service">停用</option>
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="所有者/用户"
                value={formData.owner_user || ''}
                onChange={(e) => setFormData({ ...formData, owner_user: e.target.value })}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>取消</Button>
          <Button
            onClick={selectedAsset ? handleAssign : handleScheduleMaintenance}
            variant="contained"
            sx={{ backgroundColor: '#76B900', '&:hover': { backgroundColor: '#5a8f00' } }}
          >
            {selectedAsset ? '更新' : '创建'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Asset Details Drawer */}
      <Drawer
        anchor="right"
        open={drawerOpen}
        onClose={handleDrawerClose}
        PaperProps={{
          sx: {
            width: { xs: '100%', sm: '600px', md: '700px' },
            maxWidth: '90vw',
          },
        }}
      >
        <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
          {/* Header */}
          <Box
            sx={{
              p: 3,
              backgroundColor: 'primary.main',
              color: 'white',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Typography variant="h5" sx={{ fontWeight: 'bold' }}>
                {drawerAssetLoading ? (
                  <CircularProgress size={24} sx={{ color: 'white' }} />
                ) : (
                  <>
                    <span style={{ fontSize: '1.5rem', marginRight: '8px' }}>
                      {drawerAsset ? getTypeIcon(drawerAsset.type) : '⚙️'}
                    </span>
                    {drawerAsset?.asset_id || drawerAssetId}
                  </>
                )}
              </Typography>
            </Box>
            <IconButton aria-label="关闭资产详情" onClick={handleDrawerClose} sx={{ color: 'white' }}>
              <CloseIcon />
            </IconButton>
          </Box>

          {/* Content */}
          <Box sx={{ p: 3, flex: 1, overflow: 'auto' }}>
            {drawerAssetLoading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '400px' }}>
                <CircularProgress />
              </Box>
            ) : drawerAsset ? (
              <Stack spacing={3}>
                {/* Status Card */}
                <Card sx={{ background: 'linear-gradient(135deg, #4caf50 0%, #2e7d32 100%)', color: 'white' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Box>
                        <Typography variant="overline" sx={{ opacity: 0.9 }}>
                          当前状态
                        </Typography>
                        <Typography variant="h4" sx={{ fontWeight: 'bold', mt: 1 }}>
                          {translateStatus(drawerAsset.status)}
                        </Typography>
                      </Box>
                      <Chip
                        label={translateStatus(drawerAsset.status)}
                        color={getStatusColor(drawerAsset.status) as any}
                        sx={{ 
                          backgroundColor: 'rgba(255, 255, 255, 0.2)',
                          color: 'white',
                          fontWeight: 'bold',
                          fontSize: '0.875rem',
                        }}
                      />
                    </Box>
                  </CardContent>
                </Card>

                {/* Basic Information Grid */}
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <Card sx={{ height: '100%' }}>
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                          <BuildIcon color="primary" />
                          <Typography variant="subtitle2" color="text.secondary">
                            类型
                          </Typography>
                        </Box>
                        <Typography variant="h6">{formatAssetType(drawerAsset.type)}</Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Card sx={{ height: '100%' }}>
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                          <SettingsIcon color="primary" />
                          <Typography variant="subtitle2" color="text.secondary">
                            型号
                          </Typography>
                        </Box>
                        <Typography variant="h6">{drawerAsset.model || '暂无'}</Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Card sx={{ height: '100%' }}>
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                          <LocationIcon color="primary" />
                          <Typography variant="subtitle2" color="text.secondary">
                            区域
                          </Typography>
                        </Box>
                        <Typography variant="h6">{translateWarehouseLocation(drawerAsset.zone)}</Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Card sx={{ height: '100%' }}>
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                          <PersonIcon color="primary" />
                          <Typography variant="subtitle2" color="text.secondary">
                            已分配给
                          </Typography>
                        </Box>
                        <Typography variant="h6">{drawerAsset.owner_user || '未分配'}</Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>

                {/* Manufacturing Year */}
                {drawerAsset.metadata?.manufacturing_year && (
                  <Card sx={{ background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)', color: 'white' }}>
                    <CardContent>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                        <FactoryIcon sx={{ fontSize: 40 }} />
                        <Box>
                          <Typography variant="overline" sx={{ opacity: 0.9 }}>
                            生产年份
                          </Typography>
                          <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
                            {drawerAsset.metadata.manufacturing_year}
                          </Typography>
                        </Box>
                      </Box>
                    </CardContent>
                  </Card>
                )}

                {/* Maintenance Cards */}
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <Card sx={{ borderLeft: '4px solid', borderLeftColor: 'success.main' }}>
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                          <CheckCircleIcon color="success" />
                          <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>
                            上次维护
                          </Typography>
                        </Box>
                        {drawerAsset.last_maintenance ? (
                          <Box>
                            <Typography variant="h6" sx={{ mb: 1 }}>
                              {formatZhDate(drawerAsset.last_maintenance)}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              {formatZhDateTime(drawerAsset.last_maintenance)}
                            </Typography>
                          </Box>
                        ) : (
                          <Typography variant="body2" color="text.secondary">
                            暂无维护记录
                          </Typography>
                        )}
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Card sx={{ borderLeft: '4px solid', borderLeftColor: 'warning.main' }}>
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                          <CalendarIcon color="warning" />
                          <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>
                            下次维护
                          </Typography>
                        </Box>
                        {drawerAsset.next_pm_due ? (
                          <Box>
                            <Typography variant="h6" sx={{ mb: 1 }}>
                              {formatZhDate(drawerAsset.next_pm_due)}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              还有 {Math.ceil((new Date(drawerAsset.next_pm_due).getTime() - Date.now()) / (1000 * 60 * 60 * 24))} 天
                            </Typography>
                          </Box>
                        ) : (
                          <Typography variant="body2" color="text.secondary">
                            尚未计划
                          </Typography>
                        )}
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>

                {/* Telemetry Chart */}
                {drawerTelemetry && drawerTelemetry.length > 0 && (
                  <Card>
                    <CardContent>
                      <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                        <TrendingUpIcon color="primary" />
                        遥测数据（过去 7 天）
                      </Typography>
                      {drawerTelemetryLoading ? (
                        <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
                          <CircularProgress />
                        </Box>
                      ) : (
                        <Box sx={{ height: 300 }}>
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={drawerTelemetry.slice(-50)}>
                              <CartesianGrid strokeDasharray="3 3" />
                              <XAxis 
                                dataKey="timeLabel" 
                                tick={{ fontSize: 12 }}
                                angle={-45}
                                textAnchor="end"
                                height={80}
                              />
                              <YAxis />
                              <RechartsTooltip />
                              <Legend />
                              {telemetryMetrics.length > 0 ? (
                                telemetryMetrics.map((metric: string, index: number) => {
                                  const colors = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#00ff00', '#0088fe'];
                                  return (
                                    <Line 
                                      key={metric}
                                      type="monotone" 
                                      dataKey={metric} 
                                      stroke={colors[index % colors.length]} 
                                      name={metric.replace(/_/g, ' ')}
                                      strokeWidth={2}
                                      dot={false}
                                    />
                                  );
                                })
                              ) : (
                                <Line 
                                  type="monotone" 
                                  dataKey="value" 
                                  stroke="#8884d8" 
                                  name="数值"
                                  strokeWidth={2}
                                  dot={false}
                                />
                              )}
                            </LineChart>
                          </ResponsiveContainer>
                        </Box>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* Maintenance History */}
                {drawerMaintenance && drawerMaintenance.length > 0 && (
                  <Card>
                    <CardContent>
                      <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                        <SecurityIcon color="primary" />
                        维护历史
                      </Typography>
                      <List>
                        {drawerMaintenance.slice(0, 5).map((maintenance: any, index: number) => (
                          <React.Fragment key={index}>
                            <ListItem>
                              <ListItemText
                                primary={
                                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                    <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>
                                      {maintenance.maintenance_type ? translateMaintenanceType(maintenance.maintenance_type) : '维护'}
                                    </Typography>
                                    <Chip 
                                      label={translatePriority(maintenance.priority || 'medium')} 
                                      size="small"
                                      color={maintenance.priority === 'high' ? 'error' : maintenance.priority === 'medium' ? 'warning' : 'default'}
                                    />
                                  </Box>
                                }
                                secondary={
                                  <Box>
                                    <Typography variant="body2" color="text.secondary">
                                      {maintenance.description || '暂无描述'}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">
                                      {maintenance.performed_at 
                                        ? formatZhDateTime(maintenance.performed_at)
                                        : maintenance.scheduled_for
                                        ? `计划时间：${formatZhDateTime(maintenance.scheduled_for)}`
                                        : '暂无日期'}
                                    </Typography>
                                  </Box>
                                }
                              />
                            </ListItem>
                            {index < drawerMaintenance.length - 1 && <Divider />}
                          </React.Fragment>
                        ))}
                      </List>
                    </CardContent>
                  </Card>
                )}

                {/* Additional Metadata */}
                {drawerAsset.metadata && Object.keys(drawerAsset.metadata).length > 0 && (
                  <Card>
                    <CardContent>
                      <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                        <InfoIcon color="primary" />
                        附加信息
                      </Typography>
                      <Grid container spacing={2}>
                        {Object.entries(drawerAsset.metadata)
                          .filter(([key]) => key !== 'manufacturing_year')
                          .map(([key, value]) => (
                            <Grid item xs={12} sm={6} key={key}>
                              <Box sx={{ p: 2, backgroundColor: 'grey.50', borderRadius: 1 }}>
                                <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>
                                  {key.replace(/_/g, ' ')}
                                </Typography>
                                <Typography variant="body1" sx={{ fontWeight: 'medium', mt: 0.5 }}>
                                  {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                </Typography>
                              </Box>
                            </Grid>
                          ))}
                      </Grid>
                    </CardContent>
                  </Card>
                )}
              </Stack>
            ) : (
              <Alert severity="error">资产详情加载失败</Alert>
            )}
          </Box>
        </Box>
      </Drawer>
    </Box>
  );
};

export default EquipmentNew;
