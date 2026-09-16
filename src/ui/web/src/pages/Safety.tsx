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
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import { zhCN as dataGridZhCN } from '@mui/x-data-grid/locales';
import { Report as ReportIcon } from '@mui/icons-material';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { safetyAPI, SafetyIncident, userAPI, User } from '../services/api';
import { useDialogForm } from '../components/common';
import {
  formatZhDate,
  translateRole,
  translateSafetyPolicyName,
  translateSafetyPolicySummary,
  translateStatus,
} from '../localization/zhCN';

const severityLabels: Readonly<Record<string, string>> = {
  low: '低',
  medium: '中',
  high: '高',
  critical: '严重',
};

const translateSeverity = (severity: string) => severityLabels[severity.toLowerCase()] || severity;
const translatePolicyStatus = (status: string) =>
  status.toLowerCase() === 'active' ? '有效' : translateStatus(status);

const Safety: React.FC = () => {
  const {
    open,
    setOpen,
    selectedItem: selectedIncident,
    setSelectedItem: setSelectedIncident,
    formData,
    setFormData,
    handleOpen,
    handleClose,
  } = useDialogForm<SafetyIncident>();
  const queryClient = useQueryClient();

  const { data: incidents, isLoading, error } = useQuery({
    queryKey: ['incidents'],
    queryFn: safetyAPI.getIncidents
  });

  const { data: policies } = useQuery({
    queryKey: ['policies'],
    queryFn: safetyAPI.getPolicies
  });

  const { data: users, isLoading: usersLoading, error: usersError } = useQuery({
    queryKey: ['users'],
    queryFn: userAPI.getUsers,
    retry: 2,
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
  });

  const reportMutation = useMutation({
    mutationFn: safetyAPI.reportIncident,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incidents'] });
      handleClose();
    },
  });

  const handleSubmit = () => {
    if (formData.severity && formData.description && formData.reported_by) {
      reportMutation.mutate(formData as Omit<SafetyIncident, 'id' | 'occurred_at'>);
    }
  };

  const columns: GridColDef[] = [
    { field: 'id', headerName: 'ID', width: 80 },
    {
      field: 'severity',
      headerName: '严重程度',
      width: 120,
      renderCell: (params) => {
        const severity = params.value;
        const color = severity === 'high' ? 'error' : 
                     severity === 'medium' ? 'warning' : 'info';
        return <Chip label={translateSeverity(severity)} color={color} size="small" />;
      },
    },
    { field: 'description', headerName: '事件描述', width: 300 },
    { field: 'reported_by', headerName: '报告人', width: 150 },
    {
      field: 'occurred_at',
      headerName: '发生日期',
      width: 150,
      renderCell: (params) => formatZhDate(params.value),
    },
  ];

  if (error) {
    return (
      <Box>
        <Typography variant="h4" gutterBottom>
          安全与合规
        </Typography>
        <Alert severity="error">
          安全数据加载失败，请重试。
        </Alert>
      </Box>
    );
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4">
          安全与合规
        </Typography>
        <Button
          variant="contained"
          startIcon={<ReportIcon />}
          onClick={() => handleOpen()}
        >
          报告事件
        </Button>
      </Box>

      {/* Safety Policies */}
      {policies && (
        <Paper sx={{ p: 2, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            安全政策
          </Typography>
          <Grid container spacing={2}>
            {policies.map((policy: any) => (
              <Grid item xs={12} md={6} key={policy.id}>
                <Box sx={{ p: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
                  <Typography variant="subtitle1">{translateSafetyPolicyName(policy.name)}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {translateSafetyPolicySummary(policy.summary)}
                  </Typography>
                  <Chip
                    label={translatePolicyStatus(policy.status)}
                    color={policy.status === 'Active' ? 'success' : 'default'}
                    size="small"
                    sx={{ mt: 1 }}
                  />
                </Box>
              </Grid>
            ))}
          </Grid>
        </Paper>
      )}

      {/* Incidents Management */}
      <Paper sx={{ height: 600, width: '100%' }}>
        <DataGrid
          rows={incidents || []}
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
        />
      </Paper>

      <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
        <DialogTitle>
          {selectedIncident ? '编辑事件' : '报告新事件'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>严重程度</InputLabel>
                <Select
                  value={formData.severity || ''}
                  onChange={(e) => setFormData({ ...formData, severity: e.target.value })}
                  label="严重程度"
                  required
                >
                  <MenuItem value="low">低</MenuItem>
                  <MenuItem value="medium">中</MenuItem>
                  <MenuItem value="high">高</MenuItem>
                  <MenuItem value="critical">严重</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="事件描述"
                multiline
                rows={4}
                value={formData.description || ''}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                required
              />
            </Grid>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>报告人</InputLabel>
                <Select
                  value={formData.reported_by || ''}
                  onChange={(e) => setFormData({ ...formData, reported_by: e.target.value })}
                  label="报告人"
                  required
                >
                  {usersLoading ? (
                    <MenuItem value="" disabled>正在加载用户...</MenuItem>
                  ) : usersError ? (
                    <MenuItem value="" disabled>用户加载失败</MenuItem>
                  ) : users && users.length > 0 ? (
                    users.map((user: User) => (
                      <MenuItem key={user.id} value={user.full_name || user.username}>
                        {user.full_name || user.username}（{translateRole(user.role)}）
                      </MenuItem>
                    ))
                  ) : (
                    <MenuItem value="" disabled>暂无可用用户</MenuItem>
                  )}
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>取消</Button>
          <Button
            onClick={handleSubmit}
            variant="contained"
            disabled={reportMutation.isPending}
          >
            {selectedIncident ? '更新' : '报告'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Safety;
