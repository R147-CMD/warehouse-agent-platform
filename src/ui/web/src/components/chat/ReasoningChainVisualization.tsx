import React from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Chip,
  LinearProgress,
  Tooltip,
} from '@mui/material';
import {
  Psychology as PsychologyIcon,
  Timeline as TimelineIcon,
  CheckCircle as CheckCircleIcon,
} from '@mui/icons-material';
import { ReasoningChain, ReasoningStep } from '../../services/api';

interface ReasoningChainVisualizationProps {
  reasoningChain?: ReasoningChain;
  reasoningSteps?: ReasoningStep[];
  compact?: boolean;
}

const ReasoningChainVisualization: React.FC<ReasoningChainVisualizationProps> = ({
  reasoningChain,
  reasoningSteps,
  compact = false,
}) => {
  // Use reasoningChain if available, otherwise construct from reasoningSteps
  const chain = reasoningChain || (reasoningSteps ? {
    chain_id: 'generated',
    query: '',
    reasoning_type: reasoningSteps[0]?.step_type || 'unknown',
    steps: reasoningSteps,
    final_conclusion: '',
    overall_confidence: reasoningSteps.reduce((acc, step) => acc + step.confidence, 0) / reasoningSteps.length,
  } : null);

  if (!chain) return null;

  // Normalize type once for reuse
  const normalizeType = (type: string) => type.toLowerCase();

  const getReasoningTypeColor = (type: string) => {
    const normalizedType = normalizeType(type);
    if (normalizedType.includes('causal')) return '#FF9800';
    if (normalizedType.includes('scenario')) return '#2196F3';
    if (normalizedType.includes('pattern')) return '#9C27B0';
    if (normalizedType.includes('multi')) return '#00BCD4';
    if (normalizedType.includes('chain')) return '#76B900';
    return '#666666';
  };

  const getReasoningTypeIcon = (type: string) => {
    const normalizedType = normalizeType(type);
    if (normalizedType.includes('causal')) return '🔗';
    if (normalizedType.includes('scenario')) return '🔮';
    if (normalizedType.includes('pattern')) return '🔍';
    if (normalizedType.includes('multi')) return '🔀';
    if (normalizedType.includes('chain')) return '🧠';
    return '💭';
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return '#76B900';
    if (confidence >= 0.6) return '#FF9800';
    return '#f44336';
  };

  // Constants for styling
  const CARD_STYLES = {
    main: {
      backgroundColor: '#fafafa',
      border: '1px solid #e0e0e0',
      boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    },
    step: {
      backgroundColor: 'background.paper',
      border: '1px solid #e0e0e0',
      boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
    },
    conclusion: {
      backgroundColor: '#f0f8e8',
      border: '1px solid #76B900',
      boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    },
  };

  const CHIP_STYLES = {
    type: (color: string, fontSize: string = '10px') => ({
      backgroundColor: color,
      color: '#ffffff',
      fontSize,
    }),
    confidence: (color: string, fontSize: string = '10px') => ({
      backgroundColor: color,
      color: '#ffffff',
      fontSize,
    }),
  };

  // Helper to format percentage
  const formatPercentage = (value: number, decimals: number = 0) => 
    `${(value * 100).toFixed(decimals)}%`;

  // Helper to format reasoning type label
  const formatReasoningType = (type: string) => {
    const labels: Record<string, string> = {
      chain_of_thought: '思维链',
      multi_hop: '多跳推理',
      scenario_analysis: '情景分析',
      causal: '因果推理',
      pattern_recognition: '模式识别',
      unknown: '未知类型',
    };
    return labels[normalizeType(type)] || type.replace(/_/g, ' ').toUpperCase();
  };

  // Render a single reasoning step
  const renderStep = (step: ReasoningStep, index: number, useTimelineIcon: boolean = false) => (
    <Card
      key={step.step_id || index}
      sx={{
        mt: index > 0 ? 1 : 0,
        ...CARD_STYLES.step,
      }}
    >
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          {useTimelineIcon ? (
            <TimelineIcon sx={{ color: getReasoningTypeColor(step.step_type), fontSize: 16 }} />
          ) : null}
          <Typography variant="caption" sx={{ color: '#76B900', fontWeight: 'bold' }}>
            步骤 {index + 1}
          </Typography>
          <Chip
            label={formatReasoningType(step.step_type)}
            size="small"
            sx={CHIP_STYLES.type(getReasoningTypeColor(step.step_type), '9px')}
          />
          <Box sx={{ flex: 1 }} />
          <Tooltip title={`置信度：${formatPercentage(step.confidence, 1)}`}>
            <Chip
              label={formatPercentage(step.confidence)}
              size="small"
              sx={CHIP_STYLES.confidence(getConfidenceColor(step.confidence), '9px')}
            />
          </Tooltip>
        </Box>
        <Typography variant="body2" sx={{ color: '#333333', mb: 1, fontWeight: 'bold' }}>
          {step.description}
        </Typography>
        <Typography variant="body2" sx={{ color: '#666666', fontSize: '0.875rem' }}>
          {step.reasoning}
        </Typography>
        <LinearProgress
          variant="determinate"
          value={step.confidence * 100}
          sx={{
            mt: 1,
            height: 3,
            borderRadius: 1,
            backgroundColor: '#e0e0e0',
            '& .MuiLinearProgress-bar': {
              backgroundColor: getConfidenceColor(step.confidence),
            },
          }}
        />
      </CardContent>
    </Card>
  );

  // Render final conclusion card
  const renderFinalConclusion = () => {
    if (!chain.final_conclusion) return null;
    
    return (
      <Card sx={{ mt: 2, ...CARD_STYLES.conclusion }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <CheckCircleIcon sx={{ color: '#76B900' }} />
            <Typography variant="body2" sx={{ color: '#76B900', fontWeight: 'bold' }}>
              最终结论
            </Typography>
          </Box>
          <Typography variant="body2" sx={{ color: '#333333' }}>
            {chain.final_conclusion}
          </Typography>
        </CardContent>
      </Card>
    );
  };

  if (compact) {
    // Render directly without accordion - always visible, cannot collapse
    return (
      <Box sx={{ mt: 1 }}>
        <Card sx={CARD_STYLES.main}>
          <CardContent>
            {/* Header */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <PsychologyIcon sx={{ color: getReasoningTypeColor(chain.reasoning_type) }} />
              <Typography variant="body2" sx={{ flex: 1, color: '#333333', fontWeight: 'bold' }}>
                推理链（{chain.steps?.length || 0} 个步骤）
              </Typography>
              <Chip
                label={formatReasoningType(chain.reasoning_type)}
                size="small"
                sx={CHIP_STYLES.type(getReasoningTypeColor(chain.reasoning_type), '10px')}
              />
              {chain.overall_confidence && (
                <Chip
                  label={formatPercentage(chain.overall_confidence)}
                  size="small"
                  sx={CHIP_STYLES.confidence(getConfidenceColor(chain.overall_confidence), '10px')}
                />
              )}
            </Box>
            
            {/* Content - always visible */}
            <Box>
              {chain.steps?.map((step, index) => renderStep(step, index))}
              {renderFinalConclusion()}
            </Box>
          </CardContent>
        </Card>
      </Box>
    );
  }

  return (
    <Card sx={{ mt: 1, ...CARD_STYLES.main }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
          <PsychologyIcon sx={{ color: getReasoningTypeColor(chain.reasoning_type) }} />
          <Typography variant="h6" sx={{ color: '#333333', flex: 1, fontWeight: 500 }}>
            推理链
          </Typography>
          <Chip
            label={formatReasoningType(chain.reasoning_type)}
            size="small"
            sx={CHIP_STYLES.type(getReasoningTypeColor(chain.reasoning_type))}
          />
          {chain.overall_confidence && (
            <Tooltip title={`总体置信度：${formatPercentage(chain.overall_confidence, 1)}`}>
              <Chip
                label={formatPercentage(chain.overall_confidence)}
                size="small"
                sx={CHIP_STYLES.confidence(getConfidenceColor(chain.overall_confidence))}
              />
            </Tooltip>
          )}
        </Box>

        {chain.query && (
          <Box sx={{ mb: 2, p: 1, backgroundColor: '#ffffff', borderRadius: 1, border: '1px solid #e0e0e0' }}>
            <Typography variant="caption" sx={{ color: '#666666' }}>
              查询：
            </Typography>
            <Typography variant="body2" sx={{ color: '#333333', mt: 0.5 }}>
              {chain.query}
            </Typography>
          </Box>
        )}

        <Box sx={{ mb: 2 }}>
          <Typography variant="body2" sx={{ color: '#666666', mb: 1, fontWeight: 500 }}>
            推理步骤（{chain.steps?.length || 0}）：
          </Typography>
          {chain.steps?.map((step, index) => renderStep(step, index, true))}
        </Box>

        {renderFinalConclusion()}
      </CardContent>
    </Card>
  );
};

export default ReasoningChainVisualization;

