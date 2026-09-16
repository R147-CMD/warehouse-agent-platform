import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  SelectChangeEvent,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import {
  Approval as ApprovalIcon,
  Cancel as CancelIcon,
  Refresh as RefreshIcon,
  Replay as ReplayIcon,
} from '@mui/icons-material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  AgentRun,
  AgentRunStatus,
  runAPI,
} from '../services/api';
import RunStatusBadge from '../components/runs/RunStatusBadge';
import RunTimeline from '../components/runs/RunTimeline';

const terminalStatuses = new Set<AgentRunStatus>(['completed', 'failed', 'cancelled']);

const statusOptions: Array<{ value: AgentRunStatus | ''; label: string }> = [
  { value: '', label: '全部状态' },
  { value: 'queued', label: '排队中' },
  { value: 'running', label: '执行中' },
  { value: 'waiting_approval', label: '待审批' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
  { value: 'cancel_requested', label: '取消中' },
  { value: 'cancelled', label: '已取消' },
];

const formatDateTime = (value?: string | null) => {
  if (!value) return '未知';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? '未知'
    : date.toLocaleString('zh-CN', { hour12: false });
};

const formatDuration = (run: AgentRun) => {
  if (!run.started_at) return '-';
  const start = new Date(run.started_at).getTime();
  const end = run.completed_at ? new Date(run.completed_at).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return '-';
  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) return `${seconds} 秒`;
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
};

const AgentRunCenter: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AgentRunStatus | ''>('');
  const [page] = useState(1);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(
    searchParams.get('run_id'),
  );
  const [snackbar, setSnackbar] = useState<{
    open: boolean;
    message: string;
    severity: 'success' | 'error' | 'info';
  }>({ open: false, message: '', severity: 'info' });

  const runsQuery = useQuery({
    queryKey: ['agent-runs', status, page],
    queryFn: () => runAPI.list({ status, page, page_size: 20 }),
    refetchInterval: 10000,
  });

  const detailQuery = useQuery({
    queryKey: ['agent-run-detail', selectedRunId],
    queryFn: () => runAPI.get(selectedRunId as string),
    enabled: Boolean(selectedRunId),
    refetchInterval: selectedRunId ? 10000 : false,
  });

  useEffect(() => {
    const runId = searchParams.get('run_id');
    if (runId) setSelectedRunId(runId);
  }, [searchParams]);

  useEffect(() => {
    if (!selectedRunId && runsQuery.data?.items?.length) {
      setSelectedRunId(runsQuery.data.items[0].run_id);
    }
  }, [runsQuery.data?.items, selectedRunId]);

  const selectedRun = detailQuery.data;
  const runs = runsQuery.data?.items || [];
  const total = runsQuery.data?.total || 0;
  const selectedCanCancel = selectedRun && !terminalStatuses.has(selectedRun.status);
  const selectedCanRetry = selectedRun?.status === 'failed';

  const listSummary = useMemo(() => {
    const active = runs.filter(item => item.status === 'running' || item.status === 'waiting_approval').length;
    return `共 ${total} 条，当前活跃 ${active} 条`;
  }, [runs, total]);

  const cancelMutation = useMutation({
    mutationFn: (runId: string) => runAPI.cancel(runId, '用户在任务中心请求取消'),
    onSuccess: (detail) => {
      setSnackbar({ open: true, message: '已请求取消任务', severity: 'info' });
      void queryClient.invalidateQueries({ queryKey: ['agent-runs'] });
      void queryClient.invalidateQueries({ queryKey: ['agent-run-detail', detail.run_id] });
    },
    onError: () => {
      setSnackbar({ open: true, message: '取消请求失败', severity: 'error' });
    },
  });

  const retryMutation = useMutation({
    mutationFn: (runId: string) => runAPI.retry(runId, '用户在任务中心请求重试'),
    onSuccess: (detail) => {
      setSelectedRunId(detail.run_id);
      setSearchParams({ run_id: detail.run_id });
      setSnackbar({ open: true, message: '已创建重试任务', severity: 'success' });
      void queryClient.invalidateQueries({ queryKey: ['agent-runs'] });
    },
    onError: () => {
      setSnackbar({ open: true, message: '重试创建失败', severity: 'error' });
    },
  });

  const handleStatusChange = (event: SelectChangeEvent) => {
    setStatus(event.target.value as AgentRunStatus | '');
  };

  const selectRun = (runId: string) => {
    setSelectedRunId(runId);
    setSearchParams({ run_id: runId });
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>
            任务中心
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
            {listSummary}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center">
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel id="run-status-filter-label">状态</InputLabel>
            <Select
              labelId="run-status-filter-label"
              value={status}
              label="状态"
              onChange={handleStatusChange}
            >
              {statusOptions.map(option => (
                <MenuItem key={option.value || 'all'} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={() => void runsQuery.refetch()}
          >
            刷新
          </Button>
        </Stack>
      </Stack>

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1.4fr) minmax(360px, 0.8fr)' }, gap: 2 }}>
        <Paper sx={{ overflow: 'hidden' }}>
          {runsQuery.isLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
              <CircularProgress />
            </Box>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>状态</TableCell>
                  <TableCell>任务</TableCell>
                  <TableCell>请求人</TableCell>
                  <TableCell>当前位置</TableCell>
                  <TableCell>创建时间</TableCell>
                  <TableCell>耗时</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {runs.map((run) => (
                  <TableRow
                    key={run.run_id}
                    hover
                    selected={run.run_id === selectedRunId}
                    onClick={() => selectRun(run.run_id)}
                    sx={{ cursor: 'pointer' }}
                  >
                    <TableCell><RunStatusBadge status={run.status} /></TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {run.title || '未命名任务'}
                      </Typography>
                      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                        {run.run_type}
                      </Typography>
                    </TableCell>
                    <TableCell>{run.username}</TableCell>
                    <TableCell>
                      {run.current_agent || run.current_tool || '-'}
                    </TableCell>
                    <TableCell>{formatDateTime(run.created_at)}</TableCell>
                    <TableCell>{formatDuration(run)}</TableCell>
                  </TableRow>
                ))}
                {runs.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6}>
                      <Typography variant="body2" sx={{ color: 'text.secondary', py: 3, textAlign: 'center' }}>
                        暂无任务记录
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </Paper>

        <Paper sx={{ p: 2, minHeight: 420 }}>
          {!selectedRun ? (
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              请选择一条任务记录
            </Typography>
          ) : (
            <Stack spacing={2}>
              <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                <Box>
                  <Typography variant="h6" sx={{ fontWeight: 700 }}>
                    {selectedRun.title || '未命名任务'}
                  </Typography>
                  <Typography variant="caption" sx={{ color: 'text.secondary', wordBreak: 'break-all' }}>
                    {selectedRun.run_id}
                  </Typography>
                </Box>
                <RunStatusBadge status={selectedRun.status} />
              </Stack>

              <Stack direction="row" spacing={1} flexWrap="wrap">
                {selectedRun.status === 'waiting_approval' && (
                  <Button
                    size="small"
                    variant="contained"
                    startIcon={<ApprovalIcon />}
                    onClick={() => navigate('/chat')}
                  >
                    去审批
                  </Button>
                )}
                {selectedCanCancel && (
                  <Button
                    size="small"
                    variant="outlined"
                    color="warning"
                    startIcon={<CancelIcon />}
                    disabled={cancelMutation.isPending}
                    onClick={() => cancelMutation.mutate(selectedRun.run_id)}
                  >
                    取消
                  </Button>
                )}
                {selectedCanRetry && (
                  <Button
                    size="small"
                    variant="outlined"
                    startIcon={<ReplayIcon />}
                    disabled={retryMutation.isPending}
                    onClick={() => retryMutation.mutate(selectedRun.run_id)}
                  >
                    重试
                  </Button>
                )}
              </Stack>

              <Divider />

              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  执行摘要
                </Typography>
                <Stack spacing={0.75}>
                  <Typography variant="body2">请求人：{selectedRun.username}</Typography>
                  <Typography variant="body2">创建时间：{formatDateTime(selectedRun.created_at)}</Typography>
                  <Typography variant="body2">开始时间：{formatDateTime(selectedRun.started_at)}</Typography>
                  <Typography variant="body2">结束时间：{formatDateTime(selectedRun.completed_at)}</Typography>
                  <Typography variant="body2">结果：{selectedRun.result_summary || selectedRun.error_message || '-'}</Typography>
                </Stack>
              </Box>

              <Divider />

              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  事件时间线
                </Typography>
                {detailQuery.isFetching && !detailQuery.data ? (
                  <CircularProgress size={22} />
                ) : (
                  <RunTimeline events={selectedRun.events || []} />
                )}
              </Box>
            </Stack>
          )}
        </Paper>
      </Box>

      <Snackbar
        open={snackbar.open}
        autoHideDuration={4000}
        onClose={() => setSnackbar(prev => ({ ...prev, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert
          severity={snackbar.severity}
          onClose={() => setSnackbar(prev => ({ ...prev, open: false }))}
          sx={{ width: '100%' }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default AgentRunCenter;
