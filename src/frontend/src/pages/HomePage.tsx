import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Button,
    Toast,
    ToastTitle,
    ToastBody,
    useToastController,
    Toaster
} from '@fluentui/react-components';
import { Sparkle20Filled } from '@fluentui/react-icons';
import '../styles/PlanPage.css';
import CoralShellColumn from '../coral/components/Layout/CoralShellColumn';
import CoralShellRow from '../coral/components/Layout/CoralShellRow';
import Content from '../coral/components/Content/Content';
import HomeInput from '@/components/content/HomeInput';
import { NewTaskService } from '../services/NewTaskService';
import PlanPanelLeft from '@/components/content/PlanPanelLeft';
import ContentToolbar from '@/coral/components/Content/ContentToolbar';

/**
 * HomePage component - displays task lists and provides navigation
 * Accessible via the route "/"
 */
const HomePage: React.FC = () => {
    const navigate = useNavigate();
    /**
    * Handle new task creation from the "New task" button
    * Resets textarea to empty state on HomePage
    */
    const handleNewTaskButton = useCallback(() => {
        NewTaskService.handleNewTaskFromHome();
    }, []);

    /**
     * Handle new task creation from input submission - placeholder for future implementation
     */
    const handleNewTask = useCallback((taskName: string) => {
        console.log('Creating new task:', taskName);
    }, []);

    return (
        <>
            <Toaster toasterId="toast" />
            <CoralShellColumn>
                <CoralShellRow>
                    <PlanPanelLeft
                        onNewTaskButton={handleNewTaskButton}
                    />
                    <Content>
                        <ContentToolbar
                            panelTitle={"AI VM Planner"}
                        ></ContentToolbar>
                        <HomeInput
                            onInputSubmit={handleNewTask}
                            onQuickTaskSelect={handleNewTask}
                        />
                        <div style={{ marginTop: '16px' }}>
                            <Button
                                appearance="secondary"
                                icon={<Sparkle20Filled />}
                                onClick={() => navigate('/chat')}
                            >
                                Open Risk Chat
                            </Button>
                        </div>
                    </Content>

                </CoralShellRow>
            </CoralShellColumn>
        </>
    );
};

export default HomePage;
