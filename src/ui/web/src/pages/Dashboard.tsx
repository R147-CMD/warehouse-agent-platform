import React from 'react';
import {
  Box,
  Grid,
  Paper,
  Typography,
  Card,
  CardContent,
  Chip,
} from '@mui/material';
import {
  Build as EquipmentIcon,
  Work as OperationsIcon,
  Security as SafetyIcon,
} from '@mui/icons-material';
import { useQuery } from '@tanstack/react-query';
import { healthAPI, equipmentAPI, operationsAPI, safetyAPI } from '../services/api';
import {
  formatZhDate,
  translateAssetType,
  translatePriority,
  translateStatus,
  translateTaskKind,
  translateWarehouseLocation,
} from '../localization/zhCN';

const Dashboard: React.FC = () => {
  const { data: healthStatus } = useQuery({ queryKey: ['health'], queryFn: healthAPI.check });
  const { data: equipmentAssets } = useQuery({ queryKey: ['equipment'], queryFn: equipmentAPI.getAllAssets });
  const { data: tasks } = useQuery({ queryKey: ['tasks'], queryFn: operationsAPI.getTasks });
  const { data: incidents } = useQuery({ queryKey: ['incidents'], queryFn: safetyAPI.getIncidents });

  // For equipment assets, we'll show assets that need maintenance instead of low stock
  const maintenanceNeeded = equipmentAssets?.filter(asset => 
    asset.status === 'maintenance' || 
    (asset.next_pm_due && new Date(asset.next_pm_due) <= new Date())
  ) || [];
  const pendingTasks = tasks?.filter(task => task.status === 'pending') || [];
  const recentIncidents = incidents?.slice(0, 5) || [];

  const stats = [
    {
      title: '设备资产总数',
      value: equipmentAssets?.length || 0,
      icon: <EquipmentIcon />,
      color: 'primary',
    },
    {
      title: '需要维护',
      value: maintenanceNeeded.length,
      icon: <EquipmentIcon />,
      color: 'warning',
    },
    {
      title: '待处理任务',
      value: pendingTasks.length,
      icon: <OperationsIcon />,
      color: 'info',
    },
    {
      title: '近期事件',
      value: recentIncidents.length,
      icon: <SafetyIcon />,
      color: 'error',
    },
  ];

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        仪表盘
      </Typography>
      
      {/* System Status */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Typography variant="h6">系统状态</Typography>
          <Chip
            label={healthStatus?.ok ? '在线' : '离线'}
            color={healthStatus?.ok ? 'success' : 'error'}
            variant="outlined"
          />
        </Box>
      </Paper>

      {/* Statistics Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        {stats.map((stat, index) => (
          <Grid item xs={12} sm={6} md={3} key={index}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  <Box sx={{ color: `${stat.color}.main` }}>
                    {stat.icon}
                  </Box>
                  <Box>
                    <Typography variant="h4" component="div">
                      {stat.value}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {stat.title}
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Grid container spacing={3}>
        {/* Equipment Maintenance Needed */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              待维护设备
            </Typography>
            {maintenanceNeeded.length > 0 ? (
              <Box>
                {maintenanceNeeded.map((asset) => (
                  <Box key={asset.asset_id} sx={{ mb: 2 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="body1">{asset.asset_id} - {translateAssetType(asset.type)}</Typography>
                      <Chip 
                        label={translateStatus(asset.status)}
                        color={asset.status === 'maintenance' ? 'error' : 'warning'} 
                        size="small" 
                      />
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                      型号：{asset.model || '暂无'} | 区域：{translateWarehouseLocation(asset.zone)}
                    </Typography>
                    {asset.next_pm_due && (
                      <Typography variant="body2" color="text.secondary">
                        下次预防性维护：{formatZhDate(asset.next_pm_due)}
                      </Typography>
                    )}
                  </Box>
                ))}
              </Box>
            ) : (
              <Typography color="text.secondary">所有设备状态良好</Typography>
            )}
          </Paper>
        </Grid>

        {/* Recent Tasks */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              近期任务
            </Typography>
            {pendingTasks.length > 0 ? (
              <Box>
                {pendingTasks.slice(0, 5).map((task) => (
                  <Box key={task.id} sx={{ mb: 2 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="body1">{translateTaskKind(task.kind)}</Typography>
                      <Chip label={translateStatus(task.status)} color="info" size="small" />
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                      执行人：{task.assignee || '未分配'}
                    </Typography>
                  </Box>
                ))}
              </Box>
            ) : (
              <Typography color="text.secondary">暂无待处理任务</Typography>
            )}
          </Paper>
        </Grid>

        {/* Recent Incidents */}
        <Grid item xs={12}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              近期安全事件
            </Typography>
            {recentIncidents.length > 0 ? (
              <Box>
                {recentIncidents.map((incident) => (
                  <Box key={incident.id} sx={{ mb: 2 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="body1">{incident.description}</Typography>
                      <Chip label={translatePriority(incident.severity)} color="error" size="small" />
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                      报告人：{incident.reported_by} | {formatZhDate(incident.occurred_at)}
                    </Typography>
                  </Box>
                ))}
              </Box>
            ) : (
              <Typography color="text.secondary">暂无近期安全事件</Typography>
            )}
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Dashboard;
